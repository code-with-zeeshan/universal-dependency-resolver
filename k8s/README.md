# Universal Dependency Resolver — Kubernetes Manifests

Deploy the stack into the `universal-dependency-resolver` namespace:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/frontend.yaml
kubectl apply -f k8s/ingress.yaml
```

Or apply everything at once:

```bash
kubectl apply -f k8s/
```

## Components

| Component  | Type         | Replicas | Port |
|------------|--------------|----------|------|
| backend    | Deployment   | 2        | 8000 |
| frontend   | Deployment   | 2        | 80   |
| postgres   | StatefulSet  | 1        | 5432 |
| redis      | Deployment   | 1        | 6379 |

## Ingress

- `api.yourdomain.com` → backend `:8000`
- `yourdomain.com` → frontend `:80`

TLS via cert-manager `letsencrypt-prod` cluster issuer.

## HPA (HorizontalPodAutoscaler)

Auto-scaling is configured for the backend and frontend deployments:

```bash
kubectl apply -f k8s/hpa-backend.yaml
kubectl apply -f k8s/hpa-frontend.yaml
```

| Component | Min Replicas | Max Replicas | CPU Target | Memory Target |
|-----------|-------------|-------------|------------|---------------|
| backend   | 2           | 10          | 70%        | 80%           |
| frontend  | 2           | 8           | 60%        | —             |

## PDB (PodDisruptionBudget)

PodDisruptionBudgets ensure availability during voluntary disruptions (e.g., node maintenance):

```bash
kubectl apply -f k8s/pdb-backend.yaml
kubectl apply -f k8s/pdb-frontend.yaml
```

Both enforce `minAvailable: 1`, guaranteeing at least one replica stays running.

## Network Policies

Network policies restrict pod-to-pod traffic to the minimum required:

```bash
kubectl apply -f k8s/network-policy.yaml
```

| Source              | Can Reach                   |
|---------------------|-----------------------------|
| ingress-controller  | backend, frontend           |
| frontend pods       | backend                     |
| backend pods        | postgres (5432), redis (6379)|
| (all others)        | nothing (default deny)      |

> **Note:** The network policies reference the NGINX ingress controller via the label `app.kubernetes.io/name: ingress-nginx`. If your ingress controller uses different labels, adjust the `podSelector` in `network-policy.yaml` accordingly.

## Secrets

Replace the placeholder base64 values in `secrets.yaml` before deploying to production. Generate real values with:

```bash
echo -n 'your-value' | base64
```

For GitOps workflows, consider using SealedSecrets (see `sealed-secrets-example.yaml`).

## Production Readiness Checklist

- [ ] Replace all placeholder Base64 values in `secrets.yaml` with real secrets
- [ ] Use SealedSecrets (bitnami-labs/sealed-secrets) for GitOps-friendly encrypted secrets
- [ ] Verify HPA metrics are collected (requires Metrics Server)
- [ ] Adjust resource requests/limits based on load testing
- [ ] Configure PodDisruptionBudget minAvailable to match your HA requirements
- [ ] Ensure the ingress controller is deployed and its label matches `network-policy.yaml`
- [ ] Set up ClusterIssuer for cert-manager (referenced in `ingress.yaml`)
- [ ] Add Prometheus ServiceMonitor custom resources if using prometheus-operator
- [ ] Review PersistentVolume storage classes for postgres (10Gi) and redis (5Gi)
- [ ] Enable Pod Security Standards or a policy engine (e.g., Kyverno / OPA Gatekeeper)
- [ ] Configure container image tags to pinned versions instead of `:latest`
- [ ] Set up resource quotas and limit ranges for the namespace
