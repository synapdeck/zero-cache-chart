import click


@click.group()
def main() -> None:
    """zero-cache Helm chart version manager."""


@main.command()
@click.option("--docker-image", required=True, help="Docker image to track (e.g. rocicorp/zero)")
@click.option("--chart-path", default="Chart.yaml", help="Path to Chart.yaml")
@click.option("--oci-registry", default="ghcr.io", help="OCI registry URL")
@click.option("--oci-repo", required=True, help="OCI repository path")
@click.option("--branch-retention", default=3, help="Number of major.minor branches to maintain")
@click.option("--dry-run", is_flag=True, help="Simulate without making changes")
def update(
    docker_image: str,
    chart_path: str,
    oci_registry: str,
    oci_repo: str,
    branch_retention: int,
    dry_run: bool,
) -> None:
    """Poll Docker Hub and update chart versions."""
    click.echo("Not yet implemented")


@main.command()
@click.option("--oci-registry", default="ghcr.io")
@click.option("--oci-repo", required=True)
@click.option("--max-age-days", default=7, help="Delete untagged versions older than N days")
@click.option("--all", "prune_all", is_flag=True, help="Delete ALL untagged versions regardless of age")
@click.option("--dry-run", is_flag=True)
def prune(
    oci_registry: str,
    oci_repo: str,
    max_age_days: int,
    prune_all: bool,
    dry_run: bool,
) -> None:
    """Prune untagged OCI versions from the registry."""
    click.echo("Not yet implemented")
