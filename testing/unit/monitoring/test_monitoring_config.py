#!/usr/bin/env python3
"""
Configuration Validation Tests for DS01 Monitoring Stack
/opt/ds01-infra/testing/unit/monitoring/test_monitoring_config.py

Tests that YAML, JSON, and configuration files are valid and correctly structured.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml


# =============================================================================
# Paths
# =============================================================================

MONITORING_ROOT = Path("/opt/ds01-infra/monitoring")
PROMETHEUS_DIR = MONITORING_ROOT / "prometheus"
ALERTMANAGER_DIR = MONITORING_ROOT / "alertmanager"
GRAFANA_DIR = MONITORING_ROOT / "grafana"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def prometheus_config() -> Dict[str, Any]:
    """Load and return Prometheus configuration."""
    config_path = PROMETHEUS_DIR / "prometheus.yml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def alertmanager_config() -> Dict[str, Any]:
    """Load and return Alertmanager configuration."""
    config_path = ALERTMANAGER_DIR / "alertmanager.yml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def alert_rules() -> Dict[str, Any]:
    """Load and return Prometheus alert rules."""
    rules_path = PROMETHEUS_DIR / "rules" / "ds01_alerts.yml"
    with open(rules_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def grafana_datasources() -> Dict[str, Any]:
    """Load and return Grafana datasource provisioning config."""
    config_path = GRAFANA_DIR / "provisioning" / "datasources" / "prometheus.yml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def grafana_dashboard_config() -> Dict[str, Any]:
    """Load and return Grafana dashboard provisioning config."""
    config_path = GRAFANA_DIR / "provisioning" / "dashboards" / "default.yml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def grafana_dashboard() -> Dict[str, Any]:
    """Load and return Grafana dashboard JSON."""
    dashboard_path = GRAFANA_DIR / "provisioning" / "dashboards" / "dashboards" / "ds01_overview.json"
    with open(dashboard_path) as f:
        return json.load(f)


@pytest.fixture
def docker_compose() -> Dict[str, Any]:
    """Load and return docker-compose configuration."""
    compose_path = MONITORING_ROOT / "docker-compose.yaml"
    with open(compose_path) as f:
        return yaml.safe_load(f)


# =============================================================================
# Test: YAML Files Are Valid
# =============================================================================

class TestYAMLValidity:
    """Tests that all YAML files are syntactically valid."""

    def test_prometheus_config_is_valid_yaml(self):
        """prometheus.yml should be valid YAML."""
        config_path = PROMETHEUS_DIR / "prometheus.yml"
        assert config_path.exists(), f"Config file not found: {config_path}"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config is not None, "YAML should not be empty"
        assert isinstance(config, dict), "YAML root should be a dict"

    def test_alertmanager_config_is_valid_yaml(self):
        """alertmanager.yml should be valid YAML."""
        config_path = ALERTMANAGER_DIR / "alertmanager.yml"
        assert config_path.exists(), f"Config file not found: {config_path}"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert isinstance(config, dict)

    def test_alert_rules_is_valid_yaml(self):
        """ds01_alerts.yml should be valid YAML."""
        rules_path = PROMETHEUS_DIR / "rules" / "ds01_alerts.yml"
        assert rules_path.exists(), f"Rules file not found: {rules_path}"

        with open(rules_path) as f:
            rules = yaml.safe_load(f)

        assert rules is not None
        assert isinstance(rules, dict)

    def test_grafana_datasources_is_valid_yaml(self):
        """Grafana datasources config should be valid YAML."""
        config_path = GRAFANA_DIR / "provisioning" / "datasources" / "prometheus.yml"
        assert config_path.exists(), f"Config file not found: {config_path}"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert isinstance(config, dict)

    def test_grafana_dashboard_config_is_valid_yaml(self):
        """Grafana dashboard provisioning config should be valid YAML."""
        config_path = GRAFANA_DIR / "provisioning" / "dashboards" / "default.yml"
        assert config_path.exists(), f"Config file not found: {config_path}"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert isinstance(config, dict)

    def test_docker_compose_is_valid_yaml(self):
        """docker-compose.yaml should be valid YAML."""
        compose_path = MONITORING_ROOT / "docker-compose.yaml"
        assert compose_path.exists(), f"Compose file not found: {compose_path}"

        with open(compose_path) as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert isinstance(config, dict)


# =============================================================================
# Test: JSON Files Are Valid
# =============================================================================

class TestJSONValidity:
    """Tests that all JSON files are syntactically valid."""

    def test_grafana_dashboard_is_valid_json(self):
        """Grafana dashboard JSON should be valid."""
        dashboard_path = GRAFANA_DIR / "provisioning" / "dashboards" / "dashboards" / "ds01_overview.json"
        assert dashboard_path.exists(), f"Dashboard not found: {dashboard_path}"

        with open(dashboard_path) as f:
            dashboard = json.load(f)

        assert dashboard is not None
        assert isinstance(dashboard, dict)

    def test_dashboard_has_required_fields(self, grafana_dashboard):
        """Dashboard should have essential Grafana fields."""
        required_fields = ["title", "panels", "schemaVersion"]

        for field in required_fields:
            assert field in grafana_dashboard, f"Dashboard missing required field: {field}"

    def test_dashboard_panels_have_targets(self, grafana_dashboard):
        """Dashboard panels should have query targets."""
        panels = grafana_dashboard.get("panels", [])
        assert len(panels) > 0, "Dashboard should have at least one panel"

        for panel in panels:
            if panel.get("type") not in ["row", "text"]:
                targets = panel.get("targets", [])
                assert len(targets) > 0, f"Panel '{panel.get('title')}' should have targets"


# =============================================================================
# Test: Prometheus Configuration
# =============================================================================

class TestPrometheusConfig:
    """Tests for Prometheus configuration validity."""

    def test_has_global_config(self, prometheus_config):
        """Prometheus config should have global settings."""
        assert "global" in prometheus_config
        global_config = prometheus_config["global"]

        assert "scrape_interval" in global_config
        assert "evaluation_interval" in global_config

    def test_has_required_scrape_configs(self, prometheus_config):
        """Prometheus should scrape DS01 exporter and node exporter."""
        scrape_configs = prometheus_config.get("scrape_configs", [])
        job_names = [sc.get("job_name") for sc in scrape_configs]

        assert "ds01-exporter" in job_names, "Should scrape ds01-exporter"
        assert "node-exporter" in job_names, "Should scrape node-exporter"

    def test_ds01_exporter_scrape_config(self, prometheus_config):
        """DS01 exporter scrape config should be correct."""
        scrape_configs = prometheus_config.get("scrape_configs", [])
        ds01_config = None

        for sc in scrape_configs:
            if sc.get("job_name") == "ds01-exporter":
                ds01_config = sc
                break

        assert ds01_config is not None, "ds01-exporter job not found"
        assert "static_configs" in ds01_config

        # Check target
        targets = []
        for static_config in ds01_config["static_configs"]:
            targets.extend(static_config.get("targets", []))

        assert len(targets) > 0, "ds01-exporter should have targets"
        assert any("9101" in t for t in targets), "ds01-exporter should target port 9101"

    def test_has_alertmanager_config(self, prometheus_config):
        """Prometheus should have alertmanager configured."""
        assert "alerting" in prometheus_config
        alerting = prometheus_config["alerting"]

        assert "alertmanagers" in alerting
        alertmanagers = alerting["alertmanagers"]
        assert len(alertmanagers) > 0, "Should have at least one alertmanager"

    def test_has_rule_files(self, prometheus_config):
        """Prometheus should load rule files."""
        rule_files = prometheus_config.get("rule_files", [])
        assert len(rule_files) > 0, "Should have rule files configured"


# =============================================================================
# Test: Alert Rules Configuration
# =============================================================================

class TestAlertRulesConfig:
    """Tests for Prometheus alert rules validity."""

    def test_has_rule_groups(self, alert_rules):
        """Alert rules should have groups."""
        assert "groups" in alert_rules
        groups = alert_rules["groups"]
        assert len(groups) > 0, "Should have at least one rule group"

    def test_rule_groups_have_names(self, alert_rules):
        """Each rule group should have a name."""
        groups = alert_rules.get("groups", [])

        for group in groups:
            assert "name" in group, "Rule group should have a name"
            assert group["name"], "Rule group name should not be empty"

    def test_rules_have_required_fields(self, alert_rules):
        """Each alert rule should have required fields."""
        required_fields = ["alert", "expr"]
        optional_fields = ["for", "labels", "annotations"]

        groups = alert_rules.get("groups", [])

        for group in groups:
            rules = group.get("rules", [])
            for rule in rules:
                # Check required fields
                for field in required_fields:
                    assert field in rule, f"Rule missing required field: {field} in {rule.get('alert', 'unknown')}"

    def test_rules_have_severity_labels(self, alert_rules):
        """Alert rules should have severity labels."""
        groups = alert_rules.get("groups", [])

        for group in groups:
            rules = group.get("rules", [])
            for rule in rules:
                labels = rule.get("labels", {})
                assert "severity" in labels, f"Rule '{rule.get('alert')}' should have severity label"

                # Severity should be valid
                valid_severities = ["critical", "warning", "info"]
                assert labels["severity"] in valid_severities, \
                    f"Invalid severity '{labels['severity']}' in rule '{rule.get('alert')}'"

    def test_rules_have_annotations(self, alert_rules):
        """Alert rules should have summary and description annotations."""
        groups = alert_rules.get("groups", [])

        for group in groups:
            rules = group.get("rules", [])
            for rule in rules:
                annotations = rule.get("annotations", {})
                assert "summary" in annotations, f"Rule '{rule.get('alert')}' should have summary"
                assert "description" in annotations, f"Rule '{rule.get('alert')}' should have description"

    def test_gpu_related_alerts_exist(self, alert_rules):
        """Should have GPU-related alerts."""
        groups = alert_rules.get("groups", [])
        all_alerts = []

        for group in groups:
            rules = group.get("rules", [])
            all_alerts.extend([r.get("alert") for r in rules])

        # Check for key GPU alerts
        gpu_alerts = [a for a in all_alerts if "GPU" in a]
        assert len(gpu_alerts) > 0, "Should have GPU-related alerts"

    def test_system_health_alerts_exist(self, alert_rules):
        """Should have system health alerts."""
        groups = alert_rules.get("groups", [])
        all_alerts = []

        for group in groups:
            rules = group.get("rules", [])
            all_alerts.extend([r.get("alert") for r in rules])

        # Check for exporter down alert
        assert any("ExporterDown" in a or "Down" in a for a in all_alerts), \
            "Should have exporter/service down alerts"


# =============================================================================
# Test: Alertmanager Configuration
# =============================================================================

class TestAlertmanagerConfig:
    """Tests for Alertmanager configuration validity."""

    def test_has_route(self, alertmanager_config):
        """Alertmanager should have routing configuration."""
        assert "route" in alertmanager_config
        route = alertmanager_config["route"]

        assert "receiver" in route, "Route should have default receiver"

    def test_has_receivers(self, alertmanager_config):
        """Alertmanager should have receivers defined."""
        assert "receivers" in alertmanager_config
        receivers = alertmanager_config["receivers"]
        assert len(receivers) > 0, "Should have at least one receiver"

    def test_default_receiver_exists(self, alertmanager_config):
        """Default receiver referenced in route should exist."""
        route = alertmanager_config.get("route", {})
        default_receiver = route.get("receiver")

        receivers = alertmanager_config.get("receivers", [])
        receiver_names = [r.get("name") for r in receivers]

        assert default_receiver in receiver_names, \
            f"Default receiver '{default_receiver}' not found in receivers"

    def test_has_group_by(self, alertmanager_config):
        """Route should have group_by configuration."""
        route = alertmanager_config.get("route", {})
        assert "group_by" in route, "Route should have group_by"

    def test_inhibit_rules_if_present(self, alertmanager_config):
        """If inhibit_rules exist, they should be valid."""
        inhibit_rules = alertmanager_config.get("inhibit_rules", [])

        for rule in inhibit_rules:
            # Should have source and target matchers
            has_source = "source_match" in rule or "source_matchers" in rule
            has_target = "target_match" in rule or "target_matchers" in rule or \
                         "target_match_re" in rule

            assert has_source, "Inhibit rule should have source matcher"
            assert has_target, "Inhibit rule should have target matcher"


# =============================================================================
# Test: Grafana Configuration
# =============================================================================

class TestGrafanaConfig:
    """Tests for Grafana provisioning configuration."""

    def test_datasources_has_prometheus(self, grafana_datasources):
        """Grafana should have Prometheus as a datasource."""
        datasources = grafana_datasources.get("datasources", [])
        assert len(datasources) > 0, "Should have at least one datasource"

        prometheus_ds = None
        for ds in datasources:
            if ds.get("type") == "prometheus":
                prometheus_ds = ds
                break

        assert prometheus_ds is not None, "Should have Prometheus datasource"
        assert prometheus_ds.get("url"), "Prometheus datasource should have URL"

    def test_prometheus_is_default(self, grafana_datasources):
        """Prometheus should be the default datasource."""
        datasources = grafana_datasources.get("datasources", [])

        for ds in datasources:
            if ds.get("type") == "prometheus":
                assert ds.get("isDefault", False), "Prometheus should be default datasource"
                break

    def test_dashboard_provisioning_has_path(self, grafana_dashboard_config):
        """Dashboard provisioning should have path to dashboards."""
        providers = grafana_dashboard_config.get("providers", [])
        assert len(providers) > 0, "Should have at least one dashboard provider"

        for provider in providers:
            options = provider.get("options", {})
            assert "path" in options, "Provider should have path to dashboards"


# =============================================================================
# Test: Docker Compose Configuration
# =============================================================================

class TestDockerComposeConfig:
    """Tests for docker-compose configuration."""

    def test_has_required_services(self, docker_compose):
        """Docker compose should define required services."""
        services = docker_compose.get("services", {})

        required_services = ["ds01-exporter", "prometheus", "grafana"]
        for service in required_services:
            assert service in services, f"Missing required service: {service}"

    def test_services_have_images_or_build(self, docker_compose):
        """Services should have image or build context defined."""
        services = docker_compose.get("services", {})

        for name, config in services.items():
            has_image = "image" in config
            has_build = "build" in config
            assert has_image or has_build, f"Service '{name}' needs image or build"

    def test_exporter_has_required_volumes(self, docker_compose):
        """DS01 exporter should mount required volumes."""
        services = docker_compose.get("services", {})
        exporter = services.get("ds01-exporter", {})
        volumes = exporter.get("volumes", [])

        # Check for state directory mount
        volume_paths = [v.split(":")[0] if ":" in v else v for v in volumes]

        assert any("/var/lib/ds01" in v for v in volume_paths), \
            "Exporter should mount /var/lib/ds01"
        assert any("/var/log/ds01" in v for v in volume_paths), \
            "Exporter should mount /var/log/ds01"

    def test_services_have_restart_policy(self, docker_compose):
        """Services should have restart policy for production use."""
        services = docker_compose.get("services", {})

        for name, config in services.items():
            assert "restart" in config, f"Service '{name}' should have restart policy"

    def test_ports_are_localhost_bound(self, docker_compose):
        """Service ports should be bound to localhost for security."""
        services = docker_compose.get("services", {})

        for name, config in services.items():
            ports = config.get("ports", [])
            for port in ports:
                if isinstance(port, str) and ":" in port:
                    # Format: "host:container" or "ip:host:container"
                    parts = port.split(":")
                    if len(parts) == 3:
                        # IP specified
                        ip = parts[0]
                        assert ip in ["127.0.0.1", "localhost"], \
                            f"Service '{name}' port should be localhost-bound: {port}"

    def test_has_network_defined(self, docker_compose):
        """Docker compose should define a network."""
        networks = docker_compose.get("networks", {})
        assert len(networks) > 0, "Should have at least one network defined"

    def test_prometheus_has_resource_limits(self, docker_compose):
        """Prometheus should have resource limits defined."""
        services = docker_compose.get("services", {})
        prometheus = services.get("prometheus", {})

        # Check for deploy.resources.limits or direct limits
        deploy = prometheus.get("deploy", {})
        resources = deploy.get("resources", {})
        limits = resources.get("limits", {})

        has_limits = "memory" in limits or "cpus" in limits
        assert has_limits, "Prometheus should have resource limits"


# =============================================================================
# Test: Dashboard Content
# =============================================================================

class TestDashboardContent:
    """Tests for Grafana dashboard content."""

    def test_dashboard_has_ds01_metrics(self, grafana_dashboard):
        """Dashboard should query DS01 metrics."""
        panels = grafana_dashboard.get("panels", [])

        ds01_queries = []
        for panel in panels:
            targets = panel.get("targets", [])
            for target in targets:
                expr = target.get("expr", "")
                if "ds01_" in expr:
                    ds01_queries.append(expr)

        assert len(ds01_queries) > 0, "Dashboard should have DS01 metric queries"

    def test_dashboard_has_gpu_panels(self, grafana_dashboard):
        """Dashboard should have GPU-related panels."""
        panels = grafana_dashboard.get("panels", [])
        panel_titles = [p.get("title", "").lower() for p in panels]

        gpu_panels = [t for t in panel_titles if "gpu" in t]
        assert len(gpu_panels) > 0, "Dashboard should have GPU panels"

    def test_dashboard_has_valid_panel_types(self, grafana_dashboard):
        """Dashboard panels should have valid Grafana panel types."""
        valid_types = [
            "stat", "gauge", "graph", "timeseries", "table", "piechart",
            "bargauge", "text", "row", "heatmap", "barchart", "histogram",
            "logs", "news", "nodeGraph", "canvas"
        ]

        panels = grafana_dashboard.get("panels", [])

        for panel in panels:
            panel_type = panel.get("type")
            assert panel_type in valid_types, \
                f"Invalid panel type '{panel_type}' in panel '{panel.get('title')}'"

    def test_dashboard_has_refresh_interval(self, grafana_dashboard):
        """Dashboard should have auto-refresh configured."""
        refresh = grafana_dashboard.get("refresh")
        assert refresh is not None, "Dashboard should have refresh interval"

    def test_dashboard_has_unique_panel_ids(self, grafana_dashboard):
        """Dashboard panels should have unique IDs."""
        panels = grafana_dashboard.get("panels", [])
        panel_ids = [p.get("id") for p in panels if p.get("id") is not None]

        assert len(panel_ids) == len(set(panel_ids)), "Panel IDs should be unique"
