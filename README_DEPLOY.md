# Deployment Guide | 部署指南

This guide covers multiple deployment options for Nano Banana Lab.

本指南涵盖 Nano Banana Lab 的多种部署方式。

---

## Prerequisites | 前置要求

- Google API Key (get from [Google AI Studio](https://aistudio.google.com/app/apikey))
- Python 3.10+ (for local deployment)
- Docker (for containerized deployment)

---

## 1. Local Deployment | 本地部署

### Option A: Direct Python | 直接运行

```bash
# Clone the repository
git clone https://github.com/HyxiaoGe/nano-banana-lab.git
cd nano-banana-lab

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# Run the app
streamlit run app.py
```

Access at: http://localhost:8501

### Option B: Docker | Docker 部署

```bash
# Build and run with docker-compose
export GOOGLE_API_KEY=your_api_key_here
docker-compose up -d

# Or build manually
docker build -t nano-banana-lab .
docker run -p 8501:8501 -e GOOGLE_API_KEY=your_key nano-banana-lab
```

Access at: http://localhost:8501

---

## 2. Cloud Deployment | 云平台部署

### Recommended Platforms | 推荐平台

| Platform | Pros | Cons | Cost |
|----------|------|------|------|
| **Streamlit Cloud** | Easiest, native support | Limited resources | Free |
| **Railway** | Fast deploy, good DX | Usage-based pricing | $5/month+ |
| **Render** | Auto-deploy, free tier | Cold starts on free | Free/Paid |
| **Hugging Face Spaces** | ML community, free GPU | Complex setup | Free |
| **Google Cloud Run** | Scalable, pay-per-use | Setup complexity | Pay-per-use |

---

### 2.1 Streamlit Cloud (Recommended for Quick Start)

**Steps:**

1. Push your code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click "New app"
4. Select your repository and `app.py`
5. Add secrets in "Advanced settings":
   ```toml
   GOOGLE_API_KEY = "your_api_key_here"
   ```
6. Deploy!

**Pros:**
- Free tier available
- Native Streamlit support
- Auto-deploy on push

**Limitations:**
- 1GB memory limit on free tier
- Public apps only on free tier

---

### 2.2 Railway

**Steps:**

1. Go to [railway.app](https://railway.app)
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Add environment variable: `GOOGLE_API_KEY`
5. Railway will auto-detect the `Dockerfile` or `Procfile`

**Configuration file:** `railway.json` (already included)

**Pros:**
- Great developer experience
- Auto-scaling
- Good free tier ($5 credit/month)

---

### 2.3 Render

**Steps:**

1. Go to [render.com](https://render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Set:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
5. Add environment variable: `GOOGLE_API_KEY`

**Configuration file:** `render.yaml` (already included)

**Pros:**
- Free tier available
- Auto-deploy from GitHub
- Good documentation

**Note:** Free tier has cold starts (app sleeps after 15 min inactivity)

---

### 2.4 Hugging Face Spaces

**Steps:**

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces)
2. Click "Create new Space"
3. Select "Docker" as the SDK
4. Choose "Streamlit" template
5. Upload your files or connect GitHub
6. Add secret `GOOGLE_API_KEY` in Settings → Variables and secrets

**Note:** Streamlit SDK is deprecated; use Docker SDK with Streamlit template.

**Pros:**
- Free GPU options
- Great for ML demos
- Active community

---

### 2.5 Google Cloud Run

**Steps:**

```bash
# Install gcloud CLI
# Authenticate
gcloud auth login

# Set project
gcloud config set project YOUR_PROJECT_ID

# Build and push
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/nano-banana-lab

# Deploy
gcloud run deploy nano-banana-lab \
  --image gcr.io/YOUR_PROJECT_ID/nano-banana-lab \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=your_key
```

**Pros:**
- Highly scalable
- Pay only for usage
- Global CDN

---

## 3. Environment Variables | 环境变量

All deployment methods require these environment variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Google AI API Key | Yes |

---

## 4. Troubleshooting | 故障排除

### Common Issues

**1. API Key not working**
- Ensure the key has access to Gemini Pro Image
- Check if the key is correctly set in environment variables

**2. Memory errors**
- 4K image generation requires more memory
- Use 1K/2K resolution on free tiers

**3. Cold starts on free tiers**
- First request may take 30-60 seconds
- Consider upgrading to paid tier for production

**4. Port issues**
- Ensure the app uses `$PORT` environment variable
- Streamlit default is 8501, but cloud platforms may assign different ports

---

## 5. Security Notes | 安全说明

- Never commit `.env` or `secrets.toml` to version control
- Use platform-specific secret management
- Rotate API keys periodically
- Consider rate limiting for public deployments
