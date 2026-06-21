#!/bin/bash
# monitoring/setup_monitoring.sh

echo "Setting up monitoring..."

# Check if using Grafana Cloud (free) or self-hosted
if [ "$MONITORING_TYPE" = "cloud" ]; then
    echo "Using Grafana Cloud Free Tier"
    
    # Validate credentials
    if [ -z "$GRAFANA_CLOUD_USER" ] || [ -z "$GRAFANA_CLOUD_API_KEY" ]; then
        echo "Error: Set GRAFANA_CLOUD_USER and GRAFANA_CLOUD_API_KEY"
        exit 1
    fi
    
    # Use cloud configuration
    cp prometheus-cloud.yml prometheus.yml
else
    echo "Using self-hosted monitoring"
    
    # Ensure Prometheus and Grafana are in docker-compose
    if ! grep -q "prometheus:" ../docker-compose.yml; then
        echo "Warning: Prometheus not found in docker-compose.yml"
    fi
fi

echo "Monitoring setup complete!"