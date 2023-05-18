import csv
import subprocess
import argparse
import json

report="pod_report.csv"
# Parse command-line arguments
parser = argparse.ArgumentParser(description='Extract pod information and create a CSV file.')
parser.add_argument('--exclude-ns', type=str, help='Namespaces to exclude (comma-separated)')
args = parser.parse_args()

# Check if tqdm module is available
try:
    # install tqdm for progress bar (pip install tqdm)
    from tqdm import tqdm
    use_tqdm = True
except ImportError:
    use_tqdm = False
    print("Warning: 'tqdm' module not found. Progress bar will not be displayed.")

# Run the 'oc' command to get the list of projects/namespaces
project_cmd = "oc get project -o json"
project_output = subprocess.check_output(project_cmd, shell=True)
project_data = json.loads(project_output)

# Parse the exclude-ns argument
exclude_ns = args.exclude_ns.split(",") if args.exclude_ns else []

# Create a CSV file and write the header row
csv_file = open(report, "w", newline="")
csv_writer = csv.writer(csv_file)
csv_writer.writerow(["Namespace/Project", "Name of Pod", "Name of ReplicaSet/ReplicationController",
                     "Name of Deployment/DeploymentConfig", "Name of StatefulSet", "Replicas", "Labels",
                     "HPA Name", "Min Pods", "Max Pods"])

# Iterate over each project and exclude namespaces based on exclude-ns argument
for project in project_data["items"]:
    namespace = project["metadata"]["name"]
    if any(excluded in namespace for excluded in exclude_ns):
        print(f"Skipping namespace: {namespace}")
        continue  # Skip this namespace

    # Run the 'oc' command to get the pod information in JSON format
    cmd = f"oc get pods -n {namespace} --field-selector=status.phase==Running -o json"
    output = subprocess.check_output(cmd, shell=True)

    # Parse the JSON output
    pod_data = json.loads(output)

    if use_tqdm:
        # Use tqdm for progress bar display
        progress_bar = tqdm(total=len(pod_data["items"]), desc=f"Namespace: {namespace}")

    # Iterate over each pod and extract the required information
    for pod in pod_data["items"]:
        # Extract the pod information
        pod_name = pod["metadata"]["name"]
        owner_refs = pod["metadata"].get("ownerReferences", [])
        if owner_refs:
            owner_name = owner_refs[0]["name"]
            owner_kind = owner_refs[0]["kind"]
        else:
            owner_name = ""
            owner_kind = ""

        replicas = ""
        deployment_name = ""
        replicaset_name = ""
        statefulset_name = ""
        hpa_name = ""
        min_pods = ""
        max_pods = ""

        # Check if the pod is managed by a ReplicaSet/ReplicationController
        if owner_kind in ["ReplicaSet", "ReplicationController"]:
            replicaset_name = owner_name

            # Retrieve the Deployment/DeploymentConfig name from the ReplicaSet/ReplicationController
            cmd = f"oc get {owner_kind.lower()}/{replicaset_name} -n {namespace} -o json"
            output_owner = subprocess.check_output(cmd, shell=True)
            owner_data = json.loads(output_owner)
            owner_refs = owner_data["metadata"].get("ownerReferences", [])
            if owner_refs:
                deployment_name = owner_refs[0]["name"]
                deployment_kind = owner_refs[0]["kind"]

                # Retrieve the number of replicas from the Deployment/DeploymentConfig
                cmd = f"oc get {deployment_kind.lower()}/{deployment_name} -n {namespace} -o json"
                output_deployment = subprocess.check_output(cmd, shell=True)
                deployment_data = json.loads(output_deployment)
                replicas = deployment_data["spec"].get("replicas", "")

        # Check if the pod is managed by a StatefulSet
        if owner_kind == "StatefulSet":
            statefulset_name = owner_name

        labels = pod["metadata"]["labels"] if "labels" in pod["metadata"] else ""

        # Retrieve HPA information if available
        cmd = f"oc get hpa -n {namespace} -o json"
        output_hpa = subprocess.check_output(cmd, shell=True)
        hpa_data = json.loads(output_hpa)
        for hpa in hpa_data["items"]:
            scale_target_ref = hpa["spec"].get("scaleTargetRef", {})
            if scale_target_ref.get("name") == deployment_name and scale_target_ref.get("kind") == deployment_kind:
                hpa_name = hpa["metadata"]["name"]
                min_pods = hpa["spec"].get("minReplicas", "")
                max_pods = hpa["spec"].get("maxReplicas", "")
                break

        # Write the extracted information to the CSV file
        csv_writer.writerow([namespace, pod_name, replicaset_name, deployment_name, statefulset_name, replicas,
                             labels, hpa_name, min_pods, max_pods])

        if use_tqdm:
            # Update the progress bar
            progress_bar.update(1)

    if use_tqdm:
        progress_bar.close()

# Close the CSV file
csv_file.close()

print(f"CSV file '{report}' created successfully.")
