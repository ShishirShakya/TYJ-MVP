# Load Testing Guide

**Phase 4.1: Load Testing & Performance Validation**

This directory contains load testing scripts and configurations for validating system performance under various load conditions.

## Prerequisites

Install Locust:

```bash
pip install locust
```

## Quick Start

### Basic Load Test

```bash
# Start Locust web UI
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Or run headless
locust -f tests/load/locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10 --run-time=5m --headless
```

### Environment Variables

```bash
export LOAD_TEST_API_KEY=your-api-key-here
export LOAD_TEST_HOST=http://localhost:8000
```

## Test Scenarios

### 1. Baseline Test (50 users)

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  --users=50 \
  --spawn-rate=5 \
  --run-time=10m \
  --headless
```

### 2. Stress Test (500 users)

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  --users=500 \
  --spawn-rate=50 \
  --run-time=15m \
  --headless
```

### 3. Spike Test (1000 users)

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  --users=1000 \
  --spawn-rate=100 \
  --run-time=10m \
  --headless
```

### 4. Endurance Test (200 users, 1 hour)

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  --users=200 \
  --spawn-rate=20 \
  --run-time=1h \
  --headless
```

## Test Scenarios (Python Scripts)

### Scenario 1: Realistic Exam Flow

```python
# tests/load/scenarios/exam_flow.py
# Simulates complete exam flow: question -> answer -> grade -> follow-up
```

### Scenario 2: Concurrent Sessions

```python
# tests/load/scenarios/concurrent_sessions.py
# Tests multiple concurrent exam sessions
```

### Scenario 3: API Endpoint Stress

```python
# tests/load/scenarios/api_stress.py
# Stress tests individual API endpoints
```

## Performance Targets

- **API Response Time (p95)**: < 500ms
- **Question Generation**: < 2s (p95)
- **Answer Grading**: < 3s (p95)
- **Audio Processing**: < 5s (p95)
- **Concurrent Users**: 1000+
- **Error Rate**: < 1%

## Results Analysis

After running tests, analyze:

1. **Response Times**: Check p50, p95, p99 percentiles
2. **Error Rates**: Monitor failure rates per endpoint
3. **Throughput**: Requests per second
4. **Resource Usage**: CPU, memory, network
5. **Bottlenecks**: Identify slow endpoints

## Continuous Integration

Add to CI/CD pipeline:

```yaml
# .github/workflows/load_test.yml
- name: Run Load Tests
  run: |
    locust -f tests/load/locustfile.py \
      --host=${{ env.API_URL }} \
      --users=100 \
      --spawn-rate=10 \
      --run-time=5m \
      --headless \
      --html=load_test_report.html
```

## Monitoring During Tests

Monitor these metrics during load tests:

- API response times
- Error rates
- Circuit breaker states
- Rate limiter stats
- Database/file I/O
- Memory usage
- CPU utilization

## Troubleshooting

### High Error Rates

- Check rate limiting configuration
- Verify API key is valid
- Check backend logs for errors
- Monitor circuit breaker states

### Slow Response Times

- Check database/file I/O
- Monitor OpenAI API latency
- Review caching effectiveness
- Check network latency

### Memory Leaks

- Run endurance tests (1+ hour)
- Monitor memory usage over time
- Check for unclosed connections
- Review state management

