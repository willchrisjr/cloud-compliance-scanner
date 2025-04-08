import logging
import re
from google.cloud import storage, compute_v1, resourcemanager_v3
from google.cloud.exceptions import GoogleCloudError, Forbidden

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_public_buckets(project_id: str) -> list[dict]:
    """
    Checks for publicly accessible Cloud Storage buckets in a given project.

    Args:
        project_id: The GCP project ID to scan.

    Returns:
        A list of findings, where each finding is a dictionary
        representing a non-compliant bucket.
        Returns an empty list if no public buckets are found or on error.
    """
    findings = []
    try:
        # Uses Application Default Credentials (ADC)
        storage_client = storage.Client(project=project_id)
        buckets = storage_client.list_buckets()

        for bucket in buckets:
            try:
                policy = bucket.get_iam_policy(requested_policy_version=3)
                is_public = False

                # Check for 'allUsers' or 'allAuthenticatedUsers'
                for binding in policy.bindings:
                    if binding["role"] in ["roles/storage.objectViewer", "roles/storage.legacyObjectReader"] and \
                       ("allUsers" in binding["members"] or "allAuthenticatedUsers" in binding["members"]):
                        is_public = True
                        break # Found a public binding for this bucket

                if is_public:
                    logger.warning(f"Found public bucket: {bucket.name} in project {project_id}")
                    findings.append({
                        "resource_type": "Bucket",
                        "resource_id": bucket.name,
                        "finding_description": "Bucket is publicly accessible via 'allUsers' or 'allAuthenticatedUsers'.",
                        "status": "NonCompliant",
                        "gcp_project_id": project_id # Add project_id to the finding
                    })

            except Forbidden:
                logger.error(f"Permission denied when checking IAM policy for bucket: {bucket.name} in project {project_id}. Skipping.")
            except GoogleCloudError as e:
                logger.error(f"GCP API error checking bucket {bucket.name}: {e}. Skipping.")
            except Exception as e:
                 logger.error(f"Unexpected error checking bucket {bucket.name}: {e}. Skipping.")


    except Forbidden:
        logger.error(f"Permission denied listing buckets for project: {project_id}. Ensure the service account has 'storage.buckets.list' and 'storage.buckets.getIamPolicy' permissions.")
        # Return empty list as we cannot proceed
        return []
    except GoogleCloudError as e:
        logger.error(f"GCP API error listing buckets for project {project_id}: {e}")
        # Return empty list as we cannot proceed
        return []
    except Exception as e:
        logger.error(f"Unexpected error listing buckets for project {project_id}: {e}")
        # Return empty list as we cannot proceed
        return []

    return findings

# Placeholder for other checks
def check_firewall_rules(project_id: str) -> list[dict]:
    """
    Checks for default VPC firewall rules allowing ingress from 0.0.0.0/0
    on common sensitive ports (e.g., 22, 3389).

    Args:
        project_id: The GCP project ID to scan.

    Returns:
        A list of findings for non-compliant firewall rules.
        Returns an empty list if no such rules are found or on error.
    """
    findings = []
    ports_to_check = {"22", "3389"} # TCP ports for SSH and RDP

    try:
        # Uses Application Default Credentials (ADC)
        compute_client = compute_v1.FirewallsClient()
        firewalls = compute_client.list(project=project_id)

        for rule in firewalls:
            # Check if rule is enabled, allows ingress, and targets 0.0.0.0/0
            if rule.direction == compute_v1.Firewall.Direction.INGRESS and \
               not rule.disabled and \
               "0.0.0.0/0" in rule.source_ranges:

                # Check allowed protocols and ports
                for allowed in rule.allowed:
                    # Check common protocols (TCP/UDP)
                    if allowed.ip_protocol.lower() in ["tcp", "udp"]:
                        rule_ports = set(allowed.ports)
                        # Check for overlap with sensitive ports
                        if ports_to_check.intersection(rule_ports):
                            logger.warning(f"Found potentially risky firewall rule: {rule.name} in project {project_id} allowing ingress from 0.0.0.0/0 on ports {ports_to_check.intersection(rule_ports)}")
                            findings.append({
                                "resource_type": "FirewallRule",
                                "resource_id": rule.name,
                                "finding_description": f"Rule allows ingress from 0.0.0.0/0 on sensitive ports: {', '.join(ports_to_check.intersection(rule_ports))}.",
                                "status": "NonCompliant",
                                "gcp_project_id": project_id
                            })
                            # Avoid adding the same rule multiple times if it matches multiple criteria
                            break # Move to the next rule

    except Forbidden:
        logger.error(f"Permission denied listing firewall rules for project: {project_id}. Ensure the service account has 'compute.firewalls.list' permission.")
        return []
    except GoogleCloudError as e:
        logger.error(f"GCP API error listing firewall rules for project {project_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error listing firewall rules for project {project_id}: {e}")
        return []

    return findings

def check_iam_bindings(project_id: str) -> list[dict]:
    """
    Checks for primitive roles (Owner, Editor, Viewer) assigned directly
    to user accounts or non-default service accounts at the project level.

    Args:
        project_id: The GCP project ID to scan.

    Returns:
        A list of findings for non-compliant IAM bindings.
        Returns an empty list if no such bindings are found or on error.
    """
    findings = []
    primitive_roles = {"roles/owner", "roles/editor", "roles/viewer"}
    # Regex to identify default service accounts (adjust if needed for specific envs)
    # Matches project-number-compute@..., service-project-number@... etc.
    default_sa_pattern = re.compile(
        r"^(service-|gcp-sa-|gae-api-proxy@|firebase-|\d+-compute@|\d+@cloudbuild\.gserviceaccount\.com|cloud-ml-service@|container-engine-robot@|dataproc-agent@|sourcerepo-service-agent@|cloud-filer-agent@|cloud-tasks-producer@|cloud-tasks-appengine-requester@|cloudscheduler-service-agent@|endpoints-service-agent@|remotebuildexecution-agent@|secretmanager-service-agent@|stackdriver-service-agent@|storage-transfer-service-agent@|websecurityscanner-service-agent@).*\.gserviceaccount\.com$"
    )
    # Also exclude Google-managed service accounts like P4SA
    google_managed_sa_pattern = re.compile(r"^service-\d+@gcp-sa-.*\.iam\.gserviceaccount\.com$")


    try:
        # Uses Application Default Credentials (ADC)
        crm_client = resourcemanager_v3.ProjectsClient()
        policy_request = resourcemanager_v3.GetIamPolicyRequest(
            resource=f"projects/{project_id}",
            options=resourcemanager_v3.GetPolicyOptions(requested_policy_version=3)
        )
        policy = crm_client.get_iam_policy(request=policy_request)

        for binding in policy.bindings:
            role = binding.role
            if role in primitive_roles:
                for member in binding.members:
                    member_type, member_id = member.split(":", 1)

                    # Check if it's a user or a non-default service account
                    is_user = member_type == "user"
                    is_non_default_sa = (
                        member_type == "serviceAccount" and
                        not default_sa_pattern.match(member_id) and
                        not google_managed_sa_pattern.match(member_id)
                    )

                    if is_user or is_non_default_sa:
                        logger.warning(f"Found primitive role '{role}' assigned to '{member}' in project {project_id}")
                        findings.append({
                            "resource_type": "IAMBinding",
                            "resource_id": member, # The user or SA email
                            "finding_description": f"Primitive role '{role}' assigned directly to '{member_type}'.",
                            "status": "NonCompliant",
                            "gcp_project_id": project_id
                        })

    except Forbidden:
        logger.error(f"Permission denied getting IAM policy for project: {project_id}. Ensure the service account has 'resourcemanager.projects.getIamPolicy' permission.")
        return []
    except GoogleCloudError as e:
        logger.error(f"GCP API error getting IAM policy for project {project_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error getting IAM policy for project {project_id}: {e}")
        return []

    return findings
