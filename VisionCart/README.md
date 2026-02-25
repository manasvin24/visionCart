# VisionCart – Live, Collaborative, AI-Augmented Grocery Experience

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)

## Overview

VisionCart connects a **Shopper** (wearing a POV camera) with a **Customer** (watching remotely) through a real-time, AI-enhanced video stream. The Customer sees live AI overlays—freshness scores, price comparisons, and item detection—and can interact with the Shopper's physical environment by drawing on the feed and speaking via real-time transcription.

### Key Principles

- **Low Latency Above All**: Edge-first CV inference, WebRTC direct peer connections, and optimistic state updates ensure the overlay never lags behind the video.
- **Collaborative AR**: The Customer's screen taps map to AR highlights rendered in the Shopper's viewport with sub-100ms round-trip.
- **AI-Driven Decision Support**: YOLO-based object detection, freshness heuristics, and order reconciliation run at the edge.
- **Cloud-Native Production**: Deployed on AWS with RDS Aurora, ElastiCache, ECS Fargate, and CloudFront for global scale.

---

## Tech Stack & Frameworks

### Backend
| Layer | Technology | Purpose |
|---|---|---|
| **Runtime** | Python 3.11+ | High-performance async support with asyncio |
| **Web Framework** | FastAPI | RESTful APIs, WebSocket signaling, auto-generated OpenAPI docs |
| **Async DB Driver** | asyncpg | PostgreSQL connections for Aurora (non-blocking) |
| **ORM** | SQLAlchemy 2.0 | Database abstraction, schema management, async support |
| **Validation** | Pydantic v2 | Request/response schema validation, serialization |
| **WebSocket** | python-socketio | Event-driven WebSocket server for signaling, state sync |
| **Pub/Sub** | redis-py | Redis PubSub for multi-instance horizontal scaling |
| **AI/CV** | YOLOv8 (Ultralytics) | Object detection (produce freshness, pricing) |
| **Freshness Detection** | Custom heuristics + OpenCV | Bruise scoring, color analysis, texture evaluation |
| **Voice Transcription** | OpenAI Whisper API | Real-time audio → text for customer commands |
| **Async Task Queue** | Celery (optional Phase 2) | Background jobs (session recording, analytics) |
| **Migrations** | Alembic | Database versioning, SQLite → PostgreSQL migration |
| **Logging** | Python logging + CloudWatch | Centralized observability, structured logs |

### Frontend – Customer Portal (React SPA)
| Layer | Technology | Purpose |
|---|---|---|
| **Framework** | React 18+ | Component-based UI with hooks |
| **Build Tool** | Vite | Lightning-fast bundling, HMR, production optimization |
| **Type Safety** | TypeScript 5+ | Static type checking for JS |
| **State Management** | Zustand | Lightweight state management (cart, budget, overlays) |
| **WebRTC Peer** | WebRTC API (native) | Peer-to-peer video, audio, and data channels |
| **Canvas Drawing** | HTML5 Canvas 2D | Real-time overlay rendering, customer annotations |
| **HTTP Client** | Fetch API + custom hooks | REST API calls, error handling, retries |
| **UI Components** | Custom CSS + Tailwind (optional) | Responsive design, dark mode support |
| **Styling** | CSS-in-JS / CSS Modules | Scoped styles, dynamic theming |

### Frontend – Shopper App (React Native)
| Layer | Technology | Purpose |
|---|---|---|
| **Framework** | React Native 0.72+ | Cross-platform iOS/Android mobile app |
| **Runtime** | Expo | Simplified build pipeline, OTA updates (EAS) |
| **Type Safety** | TypeScript 5+ | Mobile type safety |
| **Video Capture** | react-native-camera | POV camera stream capture |
| **WebRTC Mobile** | react-native-webrtc | WebRTC peer for mobile (iOS + Android) |
| **On-Device AI** | TensorFlow Lite (Android) / CoreML (iOS) | Edge inference, ultra-low latency |
| **State Management** | Context API + Zustand | App state, session data |
| **Navigation** | React Navigation | Stack/Tab navigation patterns |
| **HTTP/WebSocket** | AsyncStorage + Fetch/WebSocket | Offline-first data sync |
| **Geolocation** | react-native-geolocation | In-store navigation (Phase 2) |

### AI/ML Engine
| Component | Technology | Purpose |
|---|---|---|
| **Model Training** | PyTorch / TensorFlow | YOLO fine-tuning on grocery produce |
| **YOLO Inference** | YOLOv8 (PyTorch) | Real-time object detection |
| **Freshness Scoring** | Custom Python module | Bruise detection, color histogram analysis |
| **Model Export** | ONNX + TFLite | Convert to mobile-friendly formats |
| **Evaluation** | Jupyter Notebooks | Training curves, precision/recall analysis |

### Database & Caching
| Service | Local Dev | AWS Production | Purpose |
|---|---|---|---|
| **Primary DB** | SQLite (file-based) | Aurora PostgreSQL Serverless v2 | User data, orders, sessions |
| **Cache/PubSub** | Redis (Docker) | ElastiCache for Redis (cluster mode disabled) | Multi-instance state sync, real-time updates |
| **Session Store** | Redis (in-memory) | ElastiCache | WebSocket session registry, room mapping |
| **Object Storage** | MinIO (local S3 mock) | Amazon S3 | Session recordings, model weights, assets |

### Infrastructure & DevOps
| Component | Technology | Purpose |
|---|---|---|
| **Containerization** | Docker | Consistent dev/prod environments |
| **Container Orchestration (Prod)** | AWS ECS Fargate | Serverless container deployment (no server management) |
| **Service Mesh** | ALB (AWS) | Load balancing, WebSocket sticky sessions, TLS |
| **CI/CD** | GitHub Actions + AWS CodePipeline | Automated testing, building, deployment |
| **Secrets Management** | AWS Secrets Manager | Secure credential storage (API keys, DB passwords) |
| **Monitoring & Logging** | CloudWatch + X-Ray | Distributed tracing, performance metrics, alarms |
| **CDN** | CloudFront | Global content delivery for React SPA assets |
| **TURN/STUN Server** | coturn (EC2) | WebRTC NAT traversal for low-latency connectivity |

---

## Architecture

```
┌──────────────┐  WebRTC (Video/Audio/Data)  ┌──────────────┐
│  Shopper App │◄──────────────────────────►│ Customer Web │
│ (React Native)│                             │  (React SPA) │
│              │        ┌───────────┐        │              │
│  Edge AI     │◄──────►│ Signaling │◄──────►│  Canvas      │
│  (TFLite/CV) │        │  Server   │        │  Overlay     │
└──────────────┘        │ (FastAPI) │        └──────────────┘
                        └─────┬─────┘
                              │
                    ┌─────────┴─────────┐
                    │     SQLite DB     │
                    │   Redis PubSub    │
                    │   S3 / MinIO      │
                    └───────────────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for full Mermaid diagrams.

---

## Repository Structure

```
VisionCart/
├── backend/                    # FastAPI signaling + REST API server
│   ├── app/
│   │   ├── main.py             # Application entry point
│   │   ├── config.py           # Environment & settings
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── api/                # REST API routes
│   │   ├── ws/                 # WebSocket handlers (signaling, overlay, state)
│   │   ├── services/           # Business logic layer
│   │   └── ai/                 # CV inference engine
│   ├── requirements.txt
│   └── Dockerfile
├── customer-portal/            # React SPA for Customer
│   ├── src/
│   │   ├── components/         # UI components
│   │   ├── hooks/              # Custom React hooks (WebRTC, overlay)
│   │   ├── services/           # API & WebSocket clients
│   │   └── store/              # Zustand state management
│   ├── package.json
│   └── Dockerfile
├── shopper-app/                # React Native app for Shopper
│   ├── src/
│   │   ├── components/         # UI components
│   │   ├── hooks/              # Custom hooks
│   │   ├── services/           # Native modules bridge
│   │   └── ai/                 # On-device inference
│   └── package.json
├── ai-engine/                  # Standalone CV pipeline (offline training & eval)
│   ├── models/                 # YOLO weights, TFLite models
│   ├── scripts/                # Training, evaluation, export scripts
│   └── freshness/              # Freshness heuristics module
├── docs/                       # Architecture, API docs, schemas
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── SCHEMA.md
├── docker-compose.yml
├── .env.example
└── README.md                   # You are here
```

---

## Quick Start

### Prerequisites

| Tool             | Version  |
| ---------------- | -------- |
| Python           | ≥ 3.11   |
| Node.js          | ≥ 18 LTS |
| SQLite           | ≥ 3.35 (bundled with Python) |
| Redis            | ≥ 7      |
| Docker (optional)| ≥ 24     |

### 1. Clone & Configure

```bash
git clone https://github.com/your-org/visioncart.git
cd visioncart
cp .env.example .env
# Edit .env with your credentials (see Environment Variables below)
```

### 2. Docker Compose (Recommended)

```bash
docker compose up --build
```

This starts: Redis, FastAPI backend (port 8000), Customer Portal (port 3000). SQLite DB is created automatically.

### 3. Manual Setup

#### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Customer Portal
```bash
cd customer-portal
npm install
npm run dev   # Vite dev server on port 3000
```

#### Shopper App (React Native)
```bash
cd shopper-app
npm install
npx react-native run-ios   # or run-android
```

---

## Environment Variables

| Variable                   | Description                              | Default            |
| -------------------------- | ---------------------------------------- | ------------------ |
| `DATABASE_URL`             | SQLite connection string                 | `sqlite+aiosqlite:///./visioncart.db` |
| `REDIS_URL`                | Redis connection string                  | `redis://localhost` |
| `WHISPER_API_KEY`          | OpenAI Whisper API key for transcription | (optional)         |
| `AWS_ACCESS_KEY_ID`        | For S3/Kinesis (production)              | (optional)         |
| `AWS_SECRET_ACCESS_KEY`    | For S3/Kinesis (production)              | (optional)         |
| `TURN_SERVER_URL`          | TURN/STUN server for WebRTC NAT traversal| stun:stun.l.google.com:19302 |
| `TURN_SERVER_USERNAME`     | TURN credentials                         | (optional)         |
| `TURN_SERVER_CREDENTIAL`   | TURN credentials                         | (optional)         |
| `AI_MODEL_PATH`            | Path to YOLO/TFLite weights              | `./ai-engine/models/` |
| `FRESHNESS_THRESHOLD`      | Confidence threshold for bruise flagging  | `0.65`             |
| `MAX_BUDGET_ALERT_PERCENT` | Budget alert trigger (% of limit)        | `90`               |

---

## Scalability Roadmap

### Phase 1 – MVP (Current)
- Single-session 1:1 Shopper↔Customer WebRTC
- Edge-side YOLO object detection + freshness heuristics
- Canvas overlay with tap-to-highlight
- Voice transcription via Whisper API
- Budget tracking with live cart sync

### Phase 2 – Multi-Session & Analytics
- Multiple concurrent sessions via SFU (Selective Forwarding Unit)
- Session recording & replay with overlay persistence
- Historical analytics dashboard (avg. freshness scores, popular substitutions)
- Store-specific planogram integration for navigation

### Phase 3 – Platform Scale
- Agora.io / AWS Kinesis Video Streams for carrier-grade streaming
- Federated learning for freshness models across stores
- Multi-shopper orchestration (one customer, multiple shoppers)
- AR glasses integration (Vuzix, RealWear) for hands-free shopping
- Inventory API integration with major grocery chains

---

## License

MIT – see [LICENSE](LICENSE) for details.
