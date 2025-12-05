# Carris Backend API (Python/FastAPI)

Backend API service for the Carris Live bus tracking system. This service provides real-time vehicle tracking data, GTFS static data, and WebSocket support for live updates.

**Built with Python and FastAPI**

## Features

- **Real-time Vehicle Tracking**: Fetches and caches vehicle positions from Redis
- **GTFS Data API**: Access to stops, routes, shapes, and trip information from PostgreSQL
- **WebSocket Support**: Real-time updates via Socket.IO
- **REST API**: Comprehensive endpoints for all GTFS and real-time data
- **CORS Enabled**: Configured for cross-origin requests from frontend
- **Async/Await**: Fully asynchronous for high performance
- **Type Hints**: Complete type annotations for better code quality

## Prerequisites

- Python 3.11+ 
- Redis server with vehicle tracking data
- PostgreSQL with GTFS data

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file based on `.env.example`:

```env
PORT=8000
FRONTEND_URL=http://localhost:3000

REDIS_HOST=your_redis_host
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

DB_HOST=your_postgres_host
DB_PORT=5432
DB_NAME=carris_gtfs
DB_USER=your_db_user
DB_PASSWORD=your_db_password
```

## Running

### Development
```bash
uvicorn main:socket_app --reload --host 0.0.0.0 --port 8000
```

### Production
```bash
uvicorn main:socket_app --host 0.0.0.0 --port 8000 --workers 4
```

Or simply:
```bash
python main.py
```

The server will start on `http://localhost:8000`

## API Endpoints

### Vehicles
- `GET /api/vehicles` - Get all active vehicles
- `GET /api/vehicles/{vehicleId}` - Get detailed vehicle information
- `GET /api/vehicles/{vehicleId}/track` - Get vehicle track history

### Stops
- `GET /api/stops` - Get all bus stops
- `GET /api/stops/{stopId}` - Get detailed stop information
- `GET /api/stops/trip/{tripId}` - Get stops for a specific trip
- `GET /api/stops/route/{routeShortName}` - Get stops for a route

### Shapes
- `GET /api/shapes/trip/{tripId}` - Get route shape for a trip
- `GET /api/shapes/route/{routeShortName}` - Get all shapes for a route
- `GET /api/shapes/stop/{stopId}` - Get shapes for routes passing through a stop

### Health
- `GET /` - Health check and status

### WebSocket Events
- `connection` - Client connects, receives initial vehicle data
- `vehicles` - Broadcasts vehicle updates every 30 seconds
- `userCount` - Broadcasts active user count

## API Documentation

FastAPI provides interactive API documentation:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### OpenAPI Specification Files

The API is fully documented using OpenAPI 3.0.3 specification:
- **YAML format**: `openapi.yaml`
- **JSON format**: `openapi.json`

These files can be used to:
- Generate client SDKs in various languages
- Import into API testing tools (Postman, Insomnia)
- Generate documentation
- Validate requests/responses

## Docker

Build and run with Docker:

```bash
docker build -t carris-backend .
docker run -p 8000:8000 --env-file .env carris-backend
```

## Technology Stack

- **FastAPI** - Modern, fast web framework
- **Uvicorn** - ASGI server
- **Socket.IO** - WebSocket support
- **Redis** (aioredis) - Async Redis client for real-time data
- **AsyncPG** - Async PostgreSQL driver for GTFS data
- **Python 3.11+** - Latest Python with performance improvements

## Performance Benefits

- **Async I/O**: Non-blocking operations for Redis and PostgreSQL
- **Connection Pooling**: Efficient database connection management
- **Type Safety**: Pydantic models for request/response validation
- **Fast JSON**: Optimized JSON serialization
- **Auto Documentation**: Interactive API docs with Swagger UI

## Migration from Node.js

This Python backend is a complete rewrite of the Node.js backend with the following improvements:

1. **Better async handling** with native Python async/await
2. **Type safety** with type hints and Pydantic
3. **Built-in API docs** with FastAPI
4. **Simpler deployment** with fewer dependencies
5. **Better error handling** with FastAPI exception handlers
6. **Performance** comparable to or better than Node.js

All endpoints and functionality are preserved from the original Node.js implementation.

## Development

### Run with auto-reload
```bash
uvicorn main:socket_app --reload
```

### Run tests (if you add them)
```bash
pytest
```

### Type checking
```bash
mypy main.py
```

### Code formatting
```bash
black main.py
ruff check main.py
```

## Troubleshooting

### Import errors
Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### Connection errors
- Verify Redis is accessible
- Check PostgreSQL credentials
- Ensure firewall allows connections

### Port already in use
Change the PORT in `.env` or:
```bash
PORT=8001 uvicorn main:socket_app
```

## License

MIT
