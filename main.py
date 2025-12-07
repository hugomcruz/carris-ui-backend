from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import socketio
import redis.asyncio as redis
from typing import List, Dict, Any
import asyncpg
import asyncio
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration from environment variables
PORT = int(os.getenv('PORT', 8000))
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'postgres.host'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'dbname'),
    'user': os.getenv('DB_USER', 'username'),
    'password': os.getenv('DB_PASSWORD', 'password'),
}

# Redis configuration
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'redis.host'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'password': os.getenv('REDIS_PASSWORD'),
}

# Global variables for caching
vehicle_cache: List[Dict[str, Any]] = []
stops_cache: List[Dict[str, Any]] = []
stop_details_cache: Dict[str, Dict[str, Any]] = {}
redis_client = None
db_pool = None
update_task = None

# Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=FRONTEND_URL.split(',') if ',' in FRONTEND_URL else [FRONTEND_URL]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global redis_client, db_pool, update_task
    
    # Startup
    print("Starting Carris Backend API...")
    
    # Connect to Redis
    redis_client = redis.Redis(
        host=REDIS_CONFIG['host'],
        port=REDIS_CONFIG['port'],
        password=REDIS_CONFIG['password'],
        decode_responses=True
    )
    print(f"Connected to Redis at {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
    
    # Connect to PostgreSQL
    db_pool = await asyncpg.create_pool(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        database=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        min_size=5,
        max_size=10,
        command_timeout=60
    )
    print(f"Connected to PostgreSQL database: {DB_CONFIG['database']}")
    
    # Load and cache bus stops
    await load_and_cache_stops()
    
    # Initial vehicle fetch
    await fetch_and_cache_vehicles()
    
    # Start periodic update task
    update_task = asyncio.create_task(periodic_vehicle_updates())
    
    print(f"Server ready on http://localhost:{PORT}")
    
    yield
    
    # Shutdown
    print("Shutting down...")
    if update_task:
        update_task.cancel()
        try:
            await update_task
        except asyncio.CancelledError:
            pass
    
    if redis_client:
        await redis_client.close()
    
    if db_pool:
        await db_pool.close()


# Create FastAPI app
app = FastAPI(
    title="Carris Backend API",
    description="Real-time bus tracking API with Redis and PostgreSQL",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URL.split(',') if ',' in FRONTEND_URL else [FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Socket.IO
socket_app = socketio.ASGIApp(sio, app)


async def load_and_cache_stops():
    """Load and cache bus stops from database"""
    global stops_cache, stop_details_cache
    
    try:
        print('Loading bus stops from database...')
        
        query = """
            SELECT DISTINCT
                s.stop_id,
                s.stop_name,
                s.stop_lat,
                s.stop_lon,
                STRING_AGG(DISTINCT r.route_short_name, ', ' ORDER BY r.route_short_name) as routes
            FROM stops s
            LEFT JOIN stop_times st ON s.stop_id = st.stop_id
            LEFT JOIN trips t ON st.trip_id = t.trip_id
            LEFT JOIN routes r ON t.route_id = r.route_id
            WHERE s.stop_lat IS NOT NULL AND s.stop_lon IS NOT NULL
            GROUP BY s.stop_id, s.stop_name, s.stop_lat, s.stop_lon
        """
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        # Cache basic stop info
        stops_cache = [
            {
                'id': row['stop_id'],
                'lat': float(row['stop_lat']),
                'lng': float(row['stop_lon']),
                'routes': row['routes'] or ''
            }
            for row in rows
        ]
        
        # Cache detailed stop info
        stop_details_cache = {
            row['stop_id']: {
                'stop_id': row['stop_id'],
                'stop_name': row['stop_name'],
                'routes': row['routes'] or ''
            }
            for row in rows
        }
        
        print(f"Cached {len(stops_cache)} bus stops")
    except Exception as error:
        print(f"Error loading stops: {error}")


async def fetch_and_cache_vehicles():
    """Fetch and cache all vehicle data from Redis"""
    global vehicle_cache
    
    try:
        # Get all keys matching the pattern vehicle:*
        all_keys = await redis_client.keys('vehicle:*')
        keys = [key for key in all_keys if ':track' not in key]
        
        if not keys:
            vehicle_cache = []
            return
        
        # Fetch all hash values
        vehicles = []
        for key in keys:
            data = await redis_client.hgetall(key)
            if not data:
                continue
            
            vehicle_id = key.split(':')[1]
            
            # Only include vehicles with status=active
            if data.get('status') != 'active':
                continue
            
            try:
                lat = float(data.get('latitude', 0))
                lng = float(data.get('longitude', 0))
                
                if lat and lng:
                    vehicles.append({
                        'id': vehicle_id,
                        'lat': lat,
                        'lng': lng,
                        'rsn': data.get('route_short_name', 'N/A'),
                        'lp': data.get('license_plate', ''),
                        'tid': data.get('trip_id', ''),
                        'br': data.get('two_shape_bearing', data.get('bearing', '0'))
                    })
            except (ValueError, TypeError):
                continue
        
        vehicle_cache = vehicles
        print(f"Cached {len(vehicles)} vehicles from Redis")
        
        # Broadcast to all connected clients
        await sio.emit('vehicles', vehicle_cache)
    except Exception as error:
        print(f"Error fetching vehicles: {error}")


async def periodic_vehicle_updates():
    """Periodic task to update vehicles every 30 seconds"""
    while True:
        try:
            await asyncio.sleep(30)
            await fetch_and_cache_vehicles()
        except asyncio.CancelledError:
            break
        except Exception as error:
            print(f"Error in periodic update: {error}")


# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection"""
    print(f'Client connected: {sid}')
    await sio.emit('vehicles', vehicle_cache, room=sid)
    
    # Broadcast user count
    user_count = len(sio.manager.rooms.get('/', {}).keys())
    await sio.emit('userCount', user_count)


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    print(f'Client disconnected: {sid}')
    
    # Broadcast updated user count
    user_count = len(sio.manager.rooms.get('/', {}).keys())
    await sio.emit('userCount', user_count)


# REST API Endpoints

@app.get("/api/vehicles")
async def get_vehicles() -> List[Dict[str, Any]]:
    """Get all active vehicles"""
    return vehicle_cache


@app.get("/api/vehicles/{vehicle_id}")
async def get_vehicle_details(vehicle_id: str) -> Dict[str, Any]:
    """Get detailed vehicle information"""
    try:
        data = await redis_client.hgetall(f'vehicle:{vehicle_id}')
        
        if not data:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        return {
            'id': vehicle_id,
            'lat': float(data.get('latitude', 0)),
            'lng': float(data.get('longitude', 0)),
            'lp': data.get('license_plate', ''),
            'r': data.get('route_id', 'N/A'),
            'rsn': data.get('route_short_name', 'N/A'),
            'rln': data.get('route_long_name', ''),
            's': data.get('stop_id', 'N/A'),
            'sn': data.get('stop_name', ''),
            'cs': data.get('current_status', ''),
            'th': data.get('trip_headsign', ''),
            'sp': data.get('speed', ''),
            'br': data.get('two_shape_bearing', data.get('bearing', '')),
            'ts': data.get('timestamp', ''),
            'lu': data.get('last_updated', ''),
            'tid': data.get('trip_id', ''),
            'di': data.get('direction_id', ''),
            'sst': data.get('scheduled_start_time', ''),
            'set': data.get('scheduled_end_time', ''),
            'ast': data.get('actual_start_time', '')
        }
    except HTTPException:
        raise
    except Exception as error:
        print(f"Error fetching vehicle details: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch vehicle details")


@app.get("/api/vehicles/{vehicle_id}/track")
async def get_vehicle_track(vehicle_id: str) -> List[Dict[str, Any]]:
    """Get vehicle track history"""
    try:
        # Get track history from Redis sorted set
        track_data = await redis_client.zrange(
            f'vehicle:{vehicle_id}:track',
            0, -1,
            withscores=True
        )
        
        if not track_data:
            return []
        
        # Parse track data
        track = []
        for i in range(0, len(track_data), 2):
            try:
                position = json.loads(track_data[i])
                track.append({
                    'lat': float(position['latitude']),
                    'lng': float(position['longitude']),
                    'timestamp': int(track_data[i + 1])
                })
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        
        return track
    except Exception as error:
        print(f"Error fetching vehicle track: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch vehicle track")


@app.get("/api/stops")
async def get_stops() -> List[Dict[str, Any]]:
    """Get all bus stops"""
    return stops_cache


@app.get("/api/stops/trip/{trip_id}")
async def get_stops_for_trip(trip_id: str) -> List[str]:
    """Get stops for a specific trip"""
    try:
        query = """
            SELECT DISTINCT stop_id, stop_sequence 
            FROM stop_times 
            WHERE trip_id = $1 
            ORDER BY stop_sequence
        """
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, trip_id)
        
        return [row['stop_id'] for row in rows]
    except Exception as error:
        print(f"Error fetching stops for trip: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch stops")


@app.get("/api/stops/route/{route_short_name}")
async def get_stops_for_route(route_short_name: str) -> List[str]:
    """Get stops for a route"""
    try:
        query = """
            SELECT DISTINCT s.stop_id 
            FROM stops s
            JOIN stop_times st ON s.stop_id = st.stop_id
            JOIN trips t ON st.trip_id = t.trip_id
            JOIN routes r ON t.route_id = r.route_id
            WHERE r.route_short_name = $1
        """
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, route_short_name)
        
        return [row['stop_id'] for row in rows]
    except Exception as error:
        print(f"Error fetching stops for route: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch stops")


@app.get("/api/stops/{stop_id}")
async def get_stop_details(stop_id: str) -> Dict[str, Any]:
    """Get detailed stop information"""
    stop_details = stop_details_cache.get(stop_id)
    
    if not stop_details:
        raise HTTPException(status_code=404, detail="Stop not found")
    
    return stop_details


@app.get("/api/shapes/trip/{trip_id}")
async def get_shape_for_trip(trip_id: str) -> List[List[float]]:
    """Get route shape for a trip"""
    try:
        # Get shape_id from trip
        query = "SELECT shape_id FROM trips WHERE trip_id = $1 LIMIT 1"
        
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, trip_id)
        
        if not row or not row['shape_id']:
            return []
        
        shape_id = row['shape_id']
        
        # Get shape points
        query = """
            SELECT shape_pt_lat, shape_pt_lon, shape_pt_sequence 
            FROM shapes 
            WHERE shape_id = $1 
            ORDER BY shape_pt_sequence
        """
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, shape_id)
        
        return [[float(row['shape_pt_lat']), float(row['shape_pt_lon'])] for row in rows]
    except Exception as error:
        print(f"Error fetching shape: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch shape")


@app.get("/api/shapes/route/{route_short_name}")
async def get_shapes_for_route(route_short_name: str) -> List[Dict[str, Any]]:
    """Get all shapes for a route"""
    try:
        # Get outbound shape (direction_id = 0)
        query_outbound = """
            SELECT t.shape_id, COUNT(s.shape_pt_sequence) as point_count
            FROM trips t
            JOIN routes r ON t.route_id = r.route_id
            JOIN shapes s ON t.shape_id = s.shape_id
            WHERE r.route_short_name = $1 
              AND t.shape_id IS NOT NULL 
              AND (t.direction_id = '0' OR t.direction_id = 0)
            GROUP BY t.shape_id
            ORDER BY point_count DESC
            LIMIT 1
        """
        
        # Get inbound shape (direction_id = 1)
        query_inbound = """
            SELECT t.shape_id, COUNT(s.shape_pt_sequence) as point_count
            FROM trips t
            JOIN routes r ON t.route_id = r.route_id
            JOIN shapes s ON t.shape_id = s.shape_id
            WHERE r.route_short_name = $1 
              AND t.shape_id IS NOT NULL 
              AND (t.direction_id = '1' OR t.direction_id = 1)
            GROUP BY t.shape_id
            ORDER BY point_count DESC
            LIMIT 1
        """
        
        all_shapes = []
        
        async with db_pool.acquire() as conn:
            # Fetch outbound
            outbound = await conn.fetchrow(query_outbound, route_short_name)
            if outbound:
                points_query = """
                    SELECT shape_pt_lat, shape_pt_lon, shape_pt_sequence 
                    FROM shapes 
                    WHERE shape_id = $1 
                    ORDER BY shape_pt_sequence
                """
                points = await conn.fetch(points_query, outbound['shape_id'])
                if points:
                    all_shapes.append({
                        'points': [[float(p['shape_pt_lat']), float(p['shape_pt_lon'])] for p in points],
                        'direction': 0
                    })
            
            # Fetch inbound
            inbound = await conn.fetchrow(query_inbound, route_short_name)
            if inbound:
                points_query = """
                    SELECT shape_pt_lat, shape_pt_lon, shape_pt_sequence 
                    FROM shapes 
                    WHERE shape_id = $1 
                    ORDER BY shape_pt_sequence
                """
                points = await conn.fetch(points_query, inbound['shape_id'])
                if points:
                    all_shapes.append({
                        'points': [[float(p['shape_pt_lat']), float(p['shape_pt_lon'])] for p in points],
                        'direction': 1
                    })
        
        return all_shapes
    except Exception as error:
        print(f"Error fetching shapes for route: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch shapes")


@app.get("/api/shapes/stop/{stop_id}")
async def get_shapes_for_stop(stop_id: str) -> List[Dict[str, Any]]:
    """Get shapes for routes passing through a stop"""
    try:
        query = """
            SELECT DISTINCT t.shape_id, r.route_short_name
            FROM stop_times st
            JOIN trips t ON st.trip_id = t.trip_id
            JOIN routes r ON t.route_id = r.route_id
            WHERE st.stop_id = $1 AND t.shape_id IS NOT NULL
        """
        
        async with db_pool.acquire() as conn:
            shape_rows = await conn.fetch(query, stop_id)
        
        if not shape_rows:
            return []
        
        all_shapes = []
        async with db_pool.acquire() as conn:
            for shape_info in shape_rows:
                points_query = """
                    SELECT shape_pt_lat, shape_pt_lon, shape_pt_sequence 
                    FROM shapes 
                    WHERE shape_id = $1 
                    ORDER BY shape_pt_sequence
                """
                points = await conn.fetch(points_query, shape_info['shape_id'])
                
                if points:
                    all_shapes.append({
                        'route': shape_info['route_short_name'],
                        'points': [
                            {
                                'lat': float(p['shape_pt_lat']),
                                'lng': float(p['shape_pt_lon'])
                            }
                            for p in points
                        ]
                    })
        
        return all_shapes
    except Exception as error:
        print(f"Error fetching shapes for stop: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch shapes")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "message": "Carris Backend API",
        "version": "2.0.0",
        "vehicles": len(vehicle_cache),
        "stops": len(stops_cache)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(socket_app, host="0.0.0.0", port=PORT)
