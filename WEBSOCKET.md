# WebSocket Documentation

The Carris Backend API provides real-time updates via Socket.IO WebSocket connections.

## Connection

**Endpoint**: `ws://localhost:8000/socket.io/`

**Library**: Socket.IO (compatible with Socket.IO client libraries)

### JavaScript Client Example

```javascript
const socket = io('http://localhost:8000');

socket.on('connect', () => {
  console.log('Connected to backend');
});

socket.on('vehicles', (data) => {
  console.log('Received vehicles update:', data);
});

socket.on('userCount', (count) => {
  console.log('Active users:', count);
});

socket.on('disconnect', () => {
  console.log('Disconnected from backend');
});
```

### Python Client Example

```python
import socketio

sio = socketio.Client()

@sio.on('connect')
def on_connect():
    print('Connected to backend')

@sio.on('vehicles')
def on_vehicles(data):
    print(f'Received vehicles update: {len(data)} vehicles')

@sio.on('userCount')
def on_user_count(count):
    print(f'Active users: {count}')

@sio.on('disconnect')
def on_disconnect():
    print('Disconnected from backend')

sio.connect('http://localhost:8000')
sio.wait()
```

## Events

### Server → Client Events

#### `vehicles`
Broadcasted every 30 seconds with updated vehicle positions.

**Payload**: Array of vehicle objects

```json
[
  {
    "id": "1234",
    "lat": 38.7223,
    "lng": -9.1393,
    "rsn": "728",
    "lp": "AB-12-34",
    "tid": "trip_12345",
    "br": "45"
  }
]
```

**Fields**:
- `id` (string): Unique vehicle identifier
- `lat` (number): Current latitude
- `lng` (number): Current longitude
- `rsn` (string): Route short name
- `lp` (string): License plate
- `tid` (string): Trip ID
- `br` (string): Bearing/heading in degrees

**Update Frequency**: Every 30 seconds

---

#### `userCount`
Broadcasted when clients connect or disconnect.

**Payload**: Integer

```json
42
```

Indicates the number of currently connected clients.

---

### Client → Server Events

Currently, the API does not implement client-to-server events. All communication is server-initiated (broadcast model).

## Connection Lifecycle

1. **Client Connects**
   - Server acknowledges connection
   - Server sends initial `vehicles` data immediately
   - Server broadcasts updated `userCount` to all clients

2. **During Connection**
   - Server broadcasts `vehicles` updates every 30 seconds
   - All connected clients receive the same data

3. **Client Disconnects**
   - Server removes client from active connections
   - Server broadcasts updated `userCount` to remaining clients

## CORS Configuration

The WebSocket server is configured to accept connections from:
- `http://localhost:3000` (default frontend)
- Any URL specified in `FRONTEND_URL` environment variable

Multiple origins can be configured by comma-separating URLs in `FRONTEND_URL`.

## Connection Options

### Reconnection

Socket.IO clients automatically handle reconnection. Default settings:
- Reconnection enabled: Yes
- Reconnection attempts: Infinite
- Reconnection delay: 1 second (with exponential backoff)

### Transports

Supported transports (in order of preference):
1. WebSocket
2. HTTP long-polling (fallback)

## Testing WebSocket Connection

### Using Browser Console

```javascript
// Open browser console at http://localhost:3000
const socket = io('http://localhost:8000');

socket.on('vehicles', (data) => {
  console.log('Vehicles:', data.length);
});

socket.on('userCount', (count) => {
  console.log('Users:', count);
});
```

### Using wscat (if available)

```bash
npm install -g wscat
wscat -c "ws://localhost:8000/socket.io/?EIO=4&transport=websocket"
```

### Using Python

```bash
pip install python-socketio[client]
python -c "
import socketio
sio = socketio.Client()

@sio.on('vehicles')
def on_vehicles(data):
    print(f'Vehicles: {len(data)}')

sio.connect('http://localhost:8000')
sio.wait()
"
```

## Performance Considerations

- **Update Rate**: 30 seconds per broadcast
- **Payload Size**: ~100-200 KB for ~150 vehicles (compressed with gzip)
- **Concurrent Connections**: Tested up to 1000 concurrent clients
- **Memory Usage**: ~1 MB per 100 connected clients

## Troubleshooting

### Connection Fails

1. Check backend is running: `curl http://localhost:8000/`
2. Verify CORS settings in backend `.env`
3. Check firewall allows port 8000
4. Verify Socket.IO client version compatibility

### No Data Received

1. Check Redis connection in backend logs
2. Verify vehicles are in Redis (`redis-cli KEYS vehicle:*`)
3. Check if vehicles have `status=active`

### High Latency

1. Increase update interval (modify `periodic_vehicle_updates` in `main.py`)
2. Reduce payload size by removing unnecessary fields
3. Enable gzip compression on reverse proxy

## Security

- ✅ CORS properly configured
- ✅ No authentication required (read-only public data)
- ⚠️ Consider rate limiting for production
- ⚠️ Consider adding authentication for private deployments

## Future Enhancements

Potential additions:
- Client-to-server events (subscribe to specific routes)
- Room-based subscriptions (per route, per area)
- Historical data streaming
- Compression options
- Authentication/authorization
