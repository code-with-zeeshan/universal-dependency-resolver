#!/bin/bash
source "$(dirname "$0")/../scripts/common.sh"

echo "Setting up monitoring..."

if [ "$MONITORING_TYPE" = "cloud" ]; then
    echo "Using Grafana Cloud Free Tier"
    [ -z "$GRAFANA_CLOUD_USER" ] && { print_error "Set GRAFANA_CLOUD_USER"; exit 1; }
    [ -z "$GRAFANA_CLOUD_API_KEY" ] && { print_error "Set GRAFANA_CLOUD_API_KEY"; exit 1; }

    [ -f prometheus.yml ] && cp prometheus.yml "prometheus.yml.backup.$(date +%Y%m%d_%H%M%S)"
    cp prometheus-free.yml prometheus.yml
else
    echo "Using self-hosted monitoring"
    grep -q "prometheus:" ../docker-compose.yml || print_warning "Prometheus not found in docker-compose.yml"
fi

echo "Monitoring setup complete!"
