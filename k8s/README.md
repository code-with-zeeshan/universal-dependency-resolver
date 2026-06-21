# k8s/README.md
# Kubernetes Configurations

These configurations are for future scaling when moving beyond free tiers.
Currently, we recommend using:
- Render.com for backend hosting
- Vercel for frontend hosting
- Managed databases (Neon/Supabase)

## When to use these configs:
- When you need multi-region deployment
- When you exceed free tier limits
- When you need custom scaling rules

## Free Alternatives:
Instead of self-managed K8s, consider:
- Google Cloud Run (generous free tier)
- AWS ECS with Fargate spot instances
- DigitalOcean App Platform ($5 credit)

## k8s directoty structure (Future events)
```bash
k8s/
├── namespace.yaml
├── configmap.yaml
├── secrets.yaml
├── backend.yaml
├── frontend.yaml
├── postgres.yaml
├── redis.yaml
└── ingress.yaml
```