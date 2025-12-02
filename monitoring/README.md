# Monitoring & Alerting Setup

**Phase 4.2: Monitoring Dashboard & Alerting**

This directory contains configuration files for Prometheus, Grafana, and Alertmanager.

## Quick Start

### 1. Start Monitoring Stack

```bash
# Create network if it doesn't exist
docker network create vivaai-network

# Start monitoring services
docker-compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml up -d
```

### 2. Access Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093

### 3. Import Dashboards

1. Log into Grafana
2. Go to Dashboards → Import
3. Import `monitoring/grafana/dashboards/api_metrics.json`

## Configuration

### Prometheus

Edit `monitoring/prometheus/prometheus.yml` to configure:
- Scrape intervals
- Target endpoints
- Alert rules

### Grafana

Dashboards are automatically provisioned from `monitoring/grafana/dashboards/`.

### Alertmanager

Edit `monitoring/alertmanager/config.yml` to configure:
- Slack webhook URLs
- Email recipients
- Alert routing rules

## Environment Variables

Set these for Alertmanager:

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## Metrics Endpoint

The API exposes Prometheus metrics at:

```
GET /metrics?format=prometheus
```

Or use Accept header:

```bash
curl -H "Accept: text/plain" http://localhost:8000/metrics
```

## Alert Rules

Alerts are defined in `monitoring/prometheus/alerts.yml`:

- **HighErrorRate**: Error rate > 0.1 errors/sec for 5 minutes
- **SlowResponseTime**: p95 response time > 1.0s for 5 minutes
- **CircuitBreakerOpen**: Circuit breaker OPEN for 1 minute
- **HighRateLimitRejections**: Rate limit rejections > 10/sec for 5 minutes
- **HighCPUUsage**: CPU usage > 80% for 5 minutes
- **HighMemoryUsage**: Memory usage > 4GB for 5 minutes
- **ServiceDown**: Service unavailable for 1 minute

## Troubleshooting

### Prometheus not scraping

- Check target endpoints are accessible
- Verify network connectivity
- Check Prometheus logs: `docker logs vivaai-prometheus`

### Grafana can't connect to Prometheus

- Verify Prometheus is running: `docker ps`
- Check datasource URL in Grafana
- Verify network: `docker network inspect vivaai-network`

### Alerts not firing

- Check alert rules syntax: `promtool check rules monitoring/prometheus/alerts.yml`
- Verify Alertmanager is running
- Check Alertmanager logs: `docker logs vivaai-alertmanager`

## Production Deployment

For production:

1. **Secure Grafana**: Change default password, enable HTTPS
2. **Secure Prometheus**: Add authentication, enable HTTPS
3. **Configure Alerting**: Set up Slack/email/PagerDuty integrations
4. **Set Retention**: Configure Prometheus retention policy
5. **Backup**: Set up regular backups of Grafana dashboards

## Metrics Available

### API Metrics
- `vivaai_api_requests_total` - Total API requests
- `vivaai_api_request_duration_seconds` - Request duration histogram
- `vivaai_api_errors_total` - Total API errors

### Circuit Breaker Metrics
- `vivaai_circuit_breaker_state` - Circuit breaker state (0=closed, 1=half-open, 2=open)
- `vivaai_circuit_breaker_failures_total` - Total failures
- `vivaai_circuit_breaker_successes_total` - Total successes

### Rate Limiter Metrics
- `vivaai_rate_limiter_requests_total` - Total rate limiter requests
- `vivaai_rate_limiter_rejected_total` - Total rejections

### Performance Metrics
- `vivaai_question_generation_duration_seconds` - Question generation time
- `vivaai_answer_grading_duration_seconds` - Answer grading time
- `vivaai_audio_processing_duration_seconds` - Audio processing time

### Session Metrics
- `vivaai_active_sessions` - Active exam sessions
- `vivaai_completed_sessions_total` - Total completed sessions

### Cache Metrics
- `vivaai_cache_hits_total` - Cache hits
- `vivaai_cache_misses_total` - Cache misses
- `vivaai_cache_size` - Current cache size

