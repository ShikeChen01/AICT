"""Kubernetes resource manager for sandbox Pods, Services, and PVCs."""

from __future__ import annotations

import os
import secrets
from typing import Optional

from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException

import config as cfg


def _load_k8s() -> None:
    """Load K8s config — in-cluster when running in a Pod, local kubeconfig otherwise."""
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()


_load_k8s()
_core = client.CoreV1Api()

# ── Label constants ──────────────────────────────────────────────────────────

LABEL_APP = "app"
LABEL_SANDBOX_ID = "sandbox-id"
LABEL_AGENT_ID = "agent-id"
LABEL_TENANT_ID = "tenant-id"
LABEL_PROJECT_ID = "project-id"
LABEL_OS_IMAGE = "os-image"
LABEL_PERSISTENT = "persistent"

ANNOTATION_AUTH_TOKEN = "aict.dev/auth-token"
ANNOTATION_CREATED_AT = "aict.dev/created-at"
ANNOTATION_SETUP_SCRIPT = "aict.dev/setup-script-hash"


class K8sManager:
    """Manages sandbox Pods, Services, and PVCs on Kubernetes."""

    def __init__(self, namespace: str = cfg.SANDBOX_NAMESPACE) -> None:
        self._ns = namespace

    # ── Pod lifecycle ────────────────────────────────────────────────────────

    def create_sandbox_pod(
        self,
        sandbox_id: str,
        auth_token: str,
        os_image: str = cfg.DEFAULT_OS_IMAGE,
        persistent: bool = False,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> client.V1Pod:
        """Create a sandbox Pod + ClusterIP Service. Returns the created Pod."""
        catalog_entry = cfg.OS_CATALOG.get(os_image)
        if not catalog_entry:
            raise ValueError(
                f"Unknown OS image '{os_image}'. "
                f"Available: {list(cfg.OS_CATALOG.keys())}"
            )

        pod_name = f"sandbox-{sandbox_id}"
        service_name = f"sandbox-{sandbox_id}"

        labels = {
            LABEL_APP: "sandbox",
            LABEL_SANDBOX_ID: sandbox_id,
            LABEL_OS_IMAGE: os_image,
            LABEL_PERSISTENT: str(persistent).lower(),
        }
        if tenant_id:
            labels[LABEL_TENANT_ID] = tenant_id
        if project_id:
            labels[LABEL_PROJECT_ID] = project_id

        annotations = {
            ANNOTATION_AUTH_TOKEN: auth_token,
        }

        # Volume mounts — ALWAYS use PVC (no more emptyDir)
        volumes = []
        volume_mounts = []

        pvc_name = f"sandbox-pvc-{sandbox_id}"
        self._ensure_pvc(pvc_name, labels)
        volumes.append(
            client.V1Volume(
                name="workspace",
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=pvc_name,
                ),
            )
        )

        volume_mounts.append(
            client.V1VolumeMount(
                name="workspace",
                mount_path="/workspace",
            )
        )

        # Container spec
        container = client.V1Container(
            name="sandbox",
            image=catalog_entry["image"],
            ports=[
                client.V1ContainerPort(
                    container_port=cfg.CONTAINER_INTERNAL_PORT,
                    name="http",
                ),
            ],
            env=[
                client.V1EnvVar(name="AUTH_TOKEN", value=auth_token),
                client.V1EnvVar(name="SANDBOX_JWT_SECRET", value=os.environ.get("SANDBOX_JWT_SECRET", "")),
                client.V1EnvVar(name="SANDBOX_ID", value=sandbox_id),
            ],
            resources=client.V1ResourceRequirements(
                requests=catalog_entry["resources"]["requests"],
                limits=catalog_entry["resources"]["limits"],
            ),
            volume_mounts=volume_mounts,
            liveness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(
                    path="/health",
                    port=cfg.CONTAINER_INTERNAL_PORT,
                    http_headers=[
                        client.V1HTTPHeader(
                            name="Authorization",
                            value=f"Bearer {auth_token}",
                        ),
                    ],
                ),
                initial_delay_seconds=10,
                period_seconds=30,
                failure_threshold=3,
                timeout_seconds=5,
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(
                    path="/health",
                    port=cfg.CONTAINER_INTERNAL_PORT,
                    http_headers=[
                        client.V1HTTPHeader(
                            name="Authorization",
                            value=f"Bearer {auth_token}",
                        ),
                    ],
                ),
                initial_delay_seconds=5,
                period_seconds=10,
                failure_threshold=2,
                timeout_seconds=3,
            ),
        )

        # Tolerations for Windows
        tolerations = []
        for t in catalog_entry.get("tolerations", []):
            tolerations.append(
                client.V1Toleration(
                    key=t.get("key"),
                    operator=t.get("operator", "Equal"),
                    value=t.get("value"),
                    effect=t.get("effect"),
                )
            )

        # Pod spec
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=pod_name,
                namespace=self._ns,
                labels=labels,
                annotations=annotations,
            ),
            spec=client.V1PodSpec(
                containers=[container],
                volumes=volumes,
                node_selector=catalog_entry.get("node_selector", {}),
                tolerations=tolerations or None,
                restart_policy="Always",
                service_account_name="default",
                # Autopilot will auto-provision the right node type
            ),
        )

        created_pod = _core.create_namespaced_pod(
            namespace=self._ns,
            body=pod,
        )

        # Create ClusterIP Service for this Pod
        self._create_service(service_name, sandbox_id, labels)

        return created_pod

    def destroy_sandbox(self, sandbox_id: str) -> None:
        """Delete Pod, Service, and PVC for a sandbox. Idempotent."""
        pod_name = f"sandbox-{sandbox_id}"
        service_name = f"sandbox-{sandbox_id}"
        pvc_name = f"sandbox-pvc-{sandbox_id}"

        # Delete Pod
        try:
            _core.delete_namespaced_pod(
                name=pod_name,
                namespace=self._ns,
                grace_period_seconds=5,
            )
        except ApiException as e:
            if e.status != 404:
                raise

        # Delete Service
        try:
            _core.delete_namespaced_service(
                name=service_name,
                namespace=self._ns,
            )
        except ApiException as e:
            if e.status != 404:
                raise

        # Delete PVC (only if it exists)
        try:
            _core.delete_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=self._ns,
            )
        except ApiException as e:
            if e.status != 404:
                raise

    def restart_sandbox(self, sandbox_id: str) -> client.V1Pod | None:
        """
        Restart a sandbox by deleting and recreating the Pod.
        Preserves the PVC if persistent. Returns the new Pod.

        NOTE: This method is synchronous (K8s Python client is sync).
        Callers in async context should run it via asyncio.to_thread().
        """
        pod = self.get_pod(sandbox_id)
        if not pod:
            return None

        # Extract config from existing pod labels/annotations
        labels = pod.metadata.labels or {}
        annotations = pod.metadata.annotations or {}
        os_image = labels.get(LABEL_OS_IMAGE, cfg.DEFAULT_OS_IMAGE)
        persistent = labels.get(LABEL_PERSISTENT, "false") == "true"
        tenant_id = labels.get(LABEL_TENANT_ID)
        project_id = labels.get(LABEL_PROJECT_ID)
        auth_token = annotations.get(ANNOTATION_AUTH_TOKEN, secrets.token_hex(24))

        # Delete existing pod (keep PVC if persistent)
        try:
            _core.delete_namespaced_pod(
                name=f"sandbox-{sandbox_id}",
                namespace=self._ns,
                grace_period_seconds=5,
            )
        except ApiException as e:
            if e.status != 404:
                raise

        # Wait for Pod deletion to propagate before recreating.
        # Using _poll_pod_gone instead of time.sleep so we exit as soon
        # as the API confirms deletion rather than blocking a fixed 2s.
        self._poll_pod_gone(sandbox_id, timeout=10.0)

        # Recreate Pod (Service stays, PVC stays if persistent)
        return self.create_sandbox_pod(
            sandbox_id=sandbox_id,
            auth_token=auth_token,
            os_image=os_image,
            persistent=persistent,
            tenant_id=tenant_id,
            project_id=project_id,
        )

    def _poll_pod_gone(self, sandbox_id: str, timeout: float = 10.0) -> None:
        """Poll until the Pod is deleted or timeout expires."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.get_pod(sandbox_id) is None:
                return
            time.sleep(0.5)
        # Timed out — proceed anyway; create will fail loudly if name conflicts

    def get_pod(self, sandbox_id: str) -> client.V1Pod | None:
        """Get a sandbox Pod by sandbox_id."""
        try:
            return _core.read_namespaced_pod(
                name=f"sandbox-{sandbox_id}",
                namespace=self._ns,
            )
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def list_sandbox_pods(self) -> list[client.V1Pod]:
        """List all sandbox Pods in the namespace."""
        result = _core.list_namespaced_pod(
            namespace=self._ns,
            label_selector=f"{LABEL_APP}=sandbox",
        )
        return result.items

    def get_pod_status(self, sandbox_id: str) -> str:
        """Map K8s Pod phase to sandbox status string."""
        pod = self.get_pod(sandbox_id)
        if not pod:
            return "not_found"

        phase = pod.status.phase if pod.status else "Unknown"

        # Check if pod is ready (all containers ready)
        if phase == "Running":
            conditions = pod.status.conditions or []
            ready = any(
                c.type == "Ready" and c.status == "True"
                for c in conditions
            )
            return "running" if ready else "starting"

        return {
            "Pending": "starting",
            "Succeeded": "stopped",
            "Failed": "unhealthy",
            "Unknown": "unhealthy",
        }.get(phase, "unknown")

    def update_pod_labels(self, sandbox_id: str, labels: dict[str, str]) -> None:
        """Patch labels on a sandbox Pod."""
        try:
            _core.patch_namespaced_pod(
                name=f"sandbox-{sandbox_id}",
                namespace=self._ns,
                body={"metadata": {"labels": labels}},
            )
        except ApiException as e:
            if e.status != 404:
                raise

    # ── Service lifecycle ────────────────────────────────────────────────────

    def _create_service(
        self,
        service_name: str,
        sandbox_id: str,
        labels: dict[str, str],
    ) -> client.V1Service:
        """Create a ClusterIP Service targeting the sandbox Pod."""
        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=service_name,
                namespace=self._ns,
                labels=labels,
            ),
            spec=client.V1ServiceSpec(
                type="ClusterIP",
                selector={
                    LABEL_APP: "sandbox",
                    LABEL_SANDBOX_ID: sandbox_id,
                },
                ports=[
                    client.V1ServicePort(
                        name="http",
                        port=cfg.CONTAINER_INTERNAL_PORT,
                        target_port=cfg.CONTAINER_INTERNAL_PORT,
                    ),
                ],
            ),
        )
        try:
            return _core.create_namespaced_service(
                namespace=self._ns,
                body=service,
            )
        except ApiException as e:
            if e.status == 409:
                # Service already exists — that's fine
                return _core.read_namespaced_service(
                    name=service_name,
                    namespace=self._ns,
                )
            raise

    def get_service_host(self, sandbox_id: str) -> str | None:
        """Get the ClusterIP hostname for a sandbox service."""
        service_name = f"sandbox-{sandbox_id}"
        try:
            svc = _core.read_namespaced_service(
                name=service_name,
                namespace=self._ns,
            )
            # Return the in-cluster DNS name
            return f"{service_name}.{self._ns}.svc.cluster.local"
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    # ── PVC lifecycle ────────────────────────────────────────────────────────

    def _ensure_pvc(self, pvc_name: str, labels: dict[str, str]) -> None:
        """Create a PVC if it doesn't already exist."""
        try:
            _core.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=self._ns,
            )
            return  # Already exists
        except ApiException as e:
            if e.status != 404:
                raise

        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(
                name=pvc_name,
                namespace=self._ns,
                labels=labels,
            ),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                resources=client.V1VolumeResourceRequirements(
                    requests={"storage": cfg.DEFAULT_PVC_SIZE},
                ),
                # Let K8s use the default StorageClass
            ),
        )
        _core.create_namespaced_persistent_volume_claim(
            namespace=self._ns,
            body=pvc,
        )

    def delete_pvc(self, sandbox_id: str) -> None:
        """Delete the PVC for a sandbox."""
        pvc_name = f"sandbox-pvc-{sandbox_id}"
        try:
            _core.delete_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=self._ns,
            )
        except ApiException as e:
            if e.status != 404:
                raise

    # ── Volume snapshots ────────────────────────────────────────────────────────

    def create_volume_snapshot(self, sandbox_id: str, snapshot_name: str) -> dict:
        """Create a VolumeSnapshot from sandbox PVC."""
        from kubernetes.client import CustomObjectsApi
        _custom = CustomObjectsApi()
        pvc_name = f"sandbox-pvc-{sandbox_id}"
        snapshot_body = {
            "apiVersion": "snapshot.storage.k8s.io/v1",
            "kind": "VolumeSnapshot",
            "metadata": {
                "name": snapshot_name,
                "namespace": self._ns,
                "labels": {LABEL_SANDBOX_ID: sandbox_id},
            },
            "spec": {
                "volumeSnapshotClassName": "sandbox-snapshot",
                "source": {"persistentVolumeClaimName": pvc_name},
            },
        }
        result = _custom.create_namespaced_custom_object(
            group="snapshot.storage.k8s.io",
            version="v1",
            namespace=self._ns,
            plural="volumesnapshots",
            body=snapshot_body,
        )
        return {"snapshot_name": snapshot_name, "status": result.get("status", {})}

    def restore_from_snapshot(self, sandbox_id: str, snapshot_name: str) -> None:
        """Restore sandbox PVC from a VolumeSnapshot.
        1. Delete current PVC
        2. Create new PVC with dataSource pointing to snapshot
        3. Restart pod to mount new PVC
        """
        pvc_name = f"sandbox-pvc-{sandbox_id}"
        # Delete current PVC
        self.delete_pvc(sandbox_id)
        # Create PVC from snapshot
        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(
                name=pvc_name,
                namespace=self._ns,
            ),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                resources=client.V1VolumeResourceRequirements(
                    requests={"storage": cfg.DEFAULT_PVC_SIZE},
                ),
                data_source=client.V1TypedLocalObjectReference(
                    api_group="snapshot.storage.k8s.io",
                    kind="VolumeSnapshot",
                    name=snapshot_name,
                ),
            ),
        )
        _core.create_namespaced_persistent_volume_claim(namespace=self._ns, body=pvc)
        # Restart pod to mount new PVC
        self.restart_sandbox(sandbox_id)

    def list_snapshots(self, sandbox_id: str) -> list[dict]:
        """List VolumeSnapshots for a sandbox."""
        from kubernetes.client import CustomObjectsApi
        _custom = CustomObjectsApi()
        try:
            result = _custom.list_namespaced_custom_object(
                group="snapshot.storage.k8s.io",
                version="v1",
                namespace=self._ns,
                plural="volumesnapshots",
                label_selector=f"{LABEL_SANDBOX_ID}={sandbox_id}",
            )
            return [
                {
                    "name": item["metadata"]["name"],
                    "created_at": item["metadata"].get("creationTimestamp"),
                    "status": item.get("status", {}),
                }
                for item in result.get("items", [])
            ]
        except ApiException as e:
            if e.status == 404:
                return []
            raise

    def delete_snapshot(self, snapshot_name: str) -> None:
        """Delete a VolumeSnapshot."""
        from kubernetes.client import CustomObjectsApi
        _custom = CustomObjectsApi()
        try:
            _custom.delete_namespaced_custom_object(
                group="snapshot.storage.k8s.io",
                version="v1",
                namespace=self._ns,
                plural="volumesnapshots",
                name=snapshot_name,
            )
        except ApiException as e:
            if e.status != 404:
                raise
