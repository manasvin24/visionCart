# VisionCart – System Architecture

## 1. High-Level Data Flow

```mermaid
flowchart TB
    subgraph Shopper["🛒 Shopper Device (Edge)"]
        CAM[POV Camera]
        MIC[Microphone]
        EDGE_AI[Edge AI Engine<br/>TFLite / ONNX Runtime]
        AR_RENDER[AR Overlay Renderer]
        RN_APP[React Native App]
    end

    subgraph Cloud["☁️ Cloud Infrastructure"]
        SIG[Signaling Server<br/>FastAPI + WebSocket]
        REST[REST API<br/>FastAPI]
        DB[(SQLite)]
        CACHE[(Redis PubSub)]
        WHISPER[Whisper API<br/>Voice-to-Text]
        S3[Object Storage<br/>S3 / MinIO]
    end

    subgraph Customer["🖥️ Customer Portal (Browser)"]
        VIDEO[Video Player]
        CANVAS[Canvas Overlay<br/>Tap-to-Highlight]
        VOICE[Voice Input]
        DASH[Dashboard<br/>Cart / Budget / List]
        REACT_APP[React SPA]
    end

    CAM -->|MediaStream| RN_APP
    MIC -->|AudioStream| RN_APP
    RN_APP -->|Video Frames| EDGE_AI
    EDGE_AI -->|Detections + Freshness| RN_APP
    RN_APP <-->|WebRTC PeerConnection<br/>Video + Audio + DataChannel| REACT_APP

    RN_APP <-->|WebSocket<br/>Signaling / State| SIG
    REACT_APP <-->|WebSocket<br/>Signaling / State| SIG

    SIG <--> CACHE
    SIG <--> REST
    REST <--> DB
    REST <--> S3

    VOICE -->|Audio Chunks| WHISPER
    WHISPER -->|Transcription| SIG
    SIG -->|Text Notification| RN_APP

    CANVAS -->|Tap Coordinates| SIG
    SIG -->|Mapped Coordinates| AR_RENDER

    DASH <-->|Cart State| SIG
```

## 2. WebRTC Connection Flow

```mermaid
sequenceDiagram
    participant S as Shopper App
    participant SIG as Signaling Server
    participant C as Customer Portal

    Note over S,C: Session Initialization
    C->>SIG: POST /api/sessions (create session)
    SIG-->>C: { session_id, signaling_room }
    C->>SIG: WS connect (session_id, role=customer)
    S->>SIG: WS connect (session_id, role=shopper)

    Note over S,C: ICE & SDP Exchange
    S->>SIG: { type: "offer", sdp: "..." }
    SIG->>C: Forward offer
    C->>SIG: { type: "answer", sdp: "..." }
    SIG->>S: Forward answer

    loop ICE Candidates
        S->>SIG: { type: "ice-candidate", candidate: "..." }
        SIG->>C: Forward candidate
        C->>SIG: { type: "ice-candidate", candidate: "..." }
        SIG->>S: Forward candidate
    end

    Note over S,C: Peer Connection Established
    S-->>C: Video + Audio (WebRTC)
    S<-->C: DataChannel (overlay coords, AI metadata)

    Note over S,C: Real-Time Interaction
    C->>SIG: { type: "tap", x: 0.45, y: 0.32 }
    SIG->>S: Forward tap coordinates
    S->>S: Render AR highlight at (0.45, 0.32)

    C->>SIG: { type: "voice", audio: <chunk> }
    SIG->>SIG: Whisper transcription
    SIG->>S: { type: "transcript", text: "Check the expiry date" }
```

## 3. AI/CV Processing Pipeline

```mermaid
flowchart LR
    subgraph EdgePipeline["Edge AI Pipeline (< 50ms target)"]
        FRAME[Video Frame<br/>720p @ 30fps]
        PREPROCESS[Pre-process<br/>Resize 416×416<br/>Normalize]
        YOLO[YOLO v8-nano<br/>Object Detection]
        FRESH[Freshness<br/>Heuristics<br/>Color/Texture]
        RECONCILE[Order<br/>Reconciliation]
        ANNOTATE[Annotation<br/>Overlay Builder]
    end

    FRAME --> PREPROCESS
    PREPROCESS --> YOLO
    YOLO -->|Bounding Boxes<br/>+ Labels| FRESH
    YOLO -->|Detected Items| RECONCILE
    FRESH -->|Freshness Scores| ANNOTATE
    RECONCILE -->|Match Status| ANNOTATE
    ANNOTATE -->|AR Overlay Data| OUTPUT[Render to Screen<br/>+ Send via DataChannel]

    subgraph ExternalData["External Data"]
        LIST[Shopping List<br/>from Server]
        PRICES[Price DB<br/>Cached Locally]
    end

    LIST --> RECONCILE
    PRICES --> ANNOTATE
```

## 4. State Synchronization Architecture

```mermaid
flowchart TB
    subgraph StateEngine["State Sync Engine (Redis-backed)"]
        direction TB
        CART[Cart State<br/>Items + Quantities + Prices]
        BUDGET[Budget Tracker<br/>Total / Limit / Alerts]
        LIST_STATE[Shopping List State<br/>Checked / Pending / Substituted]
        SESSION[Session Metadata<br/>Duration / Quality / Events]
    end

    subgraph Publishers["Event Publishers"]
        AI_PUB[AI Engine<br/>item_detected<br/>freshness_scored]
        SHOPPER_PUB[Shopper Actions<br/>item_picked<br/>item_returned]
        CUSTOMER_PUB[Customer Actions<br/>item_approved<br/>substitute_requested]
    end

    subgraph Subscribers["Event Subscribers"]
        SHOPPER_SUB[Shopper View<br/>Updated cart overlay]
        CUSTOMER_SUB[Customer Dashboard<br/>Live cart + budget]
        ANALYTICS[Analytics Sink<br/>Session logs]
    end

    AI_PUB -->|Redis PubSub| CART
    SHOPPER_PUB -->|Redis PubSub| CART
    CUSTOMER_PUB -->|Redis PubSub| CART

    CART --> BUDGET
    CART --> LIST_STATE

    CART -->|Broadcast| SHOPPER_SUB
    CART -->|Broadcast| CUSTOMER_SUB
    BUDGET -->|Alert if > threshold| CUSTOMER_SUB
    BUDGET -->|Alert if > threshold| SHOPPER_SUB
    SESSION --> ANALYTICS
```

## 5. Coordinate Mapping System

```mermaid
flowchart LR
    TAP["Customer Tap<br/>(screenX, screenY)"]
    NORMALIZE["Normalize to<br/>[0,1] × [0,1]<br/>relative to video element"]
    TRANSFORM["Apply Homography<br/>Matrix H (3×3)<br/>if calibrated"]
    DENORM["Denormalize to<br/>Shopper Resolution<br/>(W × H)"]
    RENDER["Render Highlight<br/>Pulsing circle<br/>at (shopperX, shopperY)"]

    TAP --> NORMALIZE --> TRANSFORM --> DENORM --> RENDER

    subgraph Calibration["Optional Calibration"]
        C_POINTS["4+ Corresponding<br/>Point Pairs"]
        HOMOGRAPHY["Compute Homography<br/>cv2.findHomography()"]
    end

    C_POINTS --> HOMOGRAPHY
    HOMOGRAPHY -->|Matrix H| TRANSFORM
```

## 6. Deployment Topology

```mermaid
flowchart TB
    subgraph CDN["CDN / Edge"]
        CF[CloudFront / Cloudflare]
    end

    subgraph AppLayer["Application Layer"]
        LB[Load Balancer<br/>ALB / Nginx]
        API1[FastAPI Instance 1]
        API2[FastAPI Instance 2]
        API_N[FastAPI Instance N]
    end

    subgraph DataLayer["Data Layer"]
        PG[(SQLite)]
        RD[(Redis Cluster<br/>ElastiCache)]
        OBJ[(S3 / MinIO<br/>Object Storage)]
    end

    subgraph TURN_LAYER["TURN/STUN"]
        COTURN[coturn Server<br/>or Twilio NTS]
    end

    CF --> LB
    LB --> API1
    LB --> API2
    LB --> API_N

    API1 --> PG
    API1 --> RD
    API2 --> PG
    API2 --> RD
    API_N --> PG
    API_N --> RD

    API1 --> OBJ

    COTURN -.->|NAT Traversal| API1
```

## 7. Latency Budget

| Segment                        | Target   | Technique                          |
| ------------------------------ | -------- | ---------------------------------- |
| Camera → WebRTC encode         | < 15 ms  | Hardware H.264 encoder             |
| WebRTC transport (P2P)         | < 50 ms  | Direct peer, TURN fallback         |
| Signaling round-trip           | < 30 ms  | WebSocket, Redis PubSub            |
| Edge AI inference (YOLO-nano)  | < 25 ms  | TFLite GPU delegate, ONNX Runtime  |
| Freshness heuristic            | < 5 ms   | NumPy vectorized ops               |
| Canvas overlay render          | < 16 ms  | requestAnimationFrame, GPU canvas  |
| **End-to-end (video + overlay)** | **< 150 ms** | **Total latency budget**      |
