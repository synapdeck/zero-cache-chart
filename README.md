# Zero-Cache Helm Chart

A Helm chart for deploying [zero-cache](https://zero.rocicorp.dev/docs/deployment), the horizontally scalable service that maintains a SQLite replica of your Postgres database for the [Zero](https://zero.rocicorp.dev/) framework.

## Introduction

zero-cache is a stateful web service that maintains a SQLite replica of your Postgres database and uses this replica to sync ZQL queries to clients over WebSockets. It consists of two main components:

- **Replication Manager**: A single node that consumes the Postgres replication log and maintains the canonical SQLite replica.
- **View Syncer**: Multiple nodes that handle WebSocket connections from clients and run ZQL queries.

This Helm chart provides a cloud-agnostic way to deploy zero-cache on Kubernetes.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- An existing Postgres database with logical replication enabled (`wal_level=logical`)
- S3-compatible object storage (optional, but recommended for high availability)

## Installing the Chart

Add the repository:

```bash
helm repo add your-repo-name https://your-repo-url
helm repo update
```

To install the chart with the release name `zero-cache`:

```bash
helm install zero-cache your-repo-name/zero-cache \
  --set common.database.upstreamDb="postgres://user:password@postgres-host:5432/dbname" \
  --set common.auth.secret="your-auth-secret"
```

## Uninstalling the Chart

To uninstall/delete the `zero-cache` deployment:

```bash
helm delete zero-cache
```

## Configuration

The following table lists the configurable parameters of the zero-cache chart and their default values.

### Critical Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `common.database.upstreamDb` | Upstream Postgres database connection string | `""` (Required) |
| `common.auth.secret` | Secret for JWT authentication | `""` (One of secret/jwk/jwksUrl required) |
| `common.auth.jwk` | Public key in JWK format for JWT verification | `""` |
| `common.auth.jwksUrl` | URL that returns a JWK set for JWT verification | `""` |
| `common.replicaFile` | Path to the SQLite replica file | `/data/sync-replica.db` |
| `common.litestream.backupUrl` | S3-compatible URL for replica backup (recommended) | `""` |

### Component Sizing

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicationManager.replicas` | Number of replication manager replicas (should be 1) | `1` |
| `viewSyncer.replicas` | Number of view syncer replicas | `2` |
| `replicationManager.resources` | Resource requests and limits for replication manager | `{}` |
| `viewSyncer.resources` | Resource requests and limits for view syncer | `{}` |

### S3 Configuration (for Litestream)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `s3.enabled` | Whether to use S3 credentials | `false` |
| `s3.accessKey` | S3 access key | `""` |
| `s3.secretKey` | S3 secret key | `""` |
| `s3.region` | S3 region | `us-east-1` |
| `s3.endpoint` | S3 endpoint for alternative providers | `""` |

## Example: Deployment with MinIO

```yaml
common:
  database:
    upstreamDb: "postgres://user:password@postgres-host:5432/dbname"
  auth:
    secret: "your-auth-secret"
  litestream:
    backupUrl: "s3://zero-cache-bucket/backup"

viewSyncer:
  replicas: 3
  ingress:
    enabled: true
    hosts:
      - host: zero-cache.example.com
        paths:
          - path: /
            pathType: Prefix

s3:
  enabled: true
  accessKey: "minio-access-key"
  secretKey: "minio-secret-key"
  endpoint: "http://minio.default.svc.cluster.local:9000"
```

## Example: Deployment with AWS S3

```yaml
common:
  database:
    upstreamDb: "postgres://user:password@postgres-host:5432/dbname"
  auth:
    secret: "your-auth-secret"
  litestream:
    backupUrl: "s3://my-bucket/zero-cache-backup"

replicationManager:
  resources:
    requests:
      cpu: 500m
      memory: 1Gi

viewSyncer:
  replicas: 5
  resources:
    requests:
      cpu: 1
      memory: 2Gi

s3:
  enabled: true
  accessKey: "aws-access-key"
  secretKey: "aws-secret-key"
  region: "us-west-2"
```

## Troubleshooting

If you encounter issues with the deployment, check:

1. Postgres connection: Ensure your database is accessible and has logical replication enabled.
2. S3 credentials: Verify credentials are correct and the bucket exists.
3. Persistent volume: Ensure enough storage is allocated for your database size.
4. Logs: Check the logs of both replication-manager and view-syncer pods.

## Notes

- The replication manager must be a singleton (single replica).
- The view syncer can be scaled horizontally.
- For high availability, use a shared S3 bucket for replication.