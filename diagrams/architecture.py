from diagrams import Cluster, Diagram, Edge
from diagrams.gcp.devtools import Build, Scheduler
from diagrams.gcp.compute import Run
from diagrams.gcp.storage import GCS
from diagrams.gcp.security import SecretManager
from diagrams.onprem.vcs import Github
from diagrams.generic.device import Mobile
from diagrams.onprem.network import Internet

graph_attr = {
    "fontsize": "25",
    "bgcolor": "white",
    "pad": "0.5",
    "nodesep": "0.6",
    "ranksep": "0.75",
    "splines": "spline",
    "labelloc": "t"
}

with Diagram("Pixel Build Pipeline Architecture", show=False, filename="diagrams/pixel_architecture_v3", graph_attr=graph_attr, direction="LR"):

    with Cluster("External World"):
        developer = Github("GitHub Repo\n(Push to main)")
        google_servers = Internet("Google Factory\nImages")
        user_phone = Mobile("Pixel Phone")
        
        developer - Edge(style="invis") - google_servers - Edge(style="invis") - user_phone

    with Cluster("Google Cloud Platform"):
        
        with Cluster("1. CI/CD & Logic"):
            # Trigger -> Build -> Deploy Job
            scheduler = Scheduler("Cloud Scheduler\n(Every 24h)")
            builder = Build("Cloud Build\n(Build & Deploy)")
            automator = Run("Cloud Run Job\n(Pixel Automator)")

        with Cluster("2. Storage"):
            bucket = GCS("GCS Bucket\n(Cache & Artifacts)")
        
        with Cluster("3. Security"):
            secrets = SecretManager("Secret Manager\n(AVB Keys)")

    # --- Relationships ---

    # 1. Trigger
    developer >> Edge(label="Trigger Build", color="darkorange", minlen="2.0") >> builder
    builder >> Edge(label="Deploy/Update", style="bold") >> automator
    scheduler >> Edge(label="Trigger Job", style="dashed") >> automator

    # 2. Dependencies
    automator >> Edge(label="Fetch Keys", color="red", style="bold") >> secrets
    automator >> Edge(label="Check/Download", color="blue", style="dashed") >> google_servers

    # 3. Cache & Artifacts
    automator >> Edge(label="Check Cache", color="black") >> bucket
    automator >> Edge(label="Upload Artifacts", color="darkgreen", style="bold") >> bucket

    # 4. Deployment/Update
    bucket >> Edge(label="Download OTA", color="green", style="bold", minlen="2.0") >> user_phone

print("Diagram generated as diagrams/pixel_architecture_v3.png")
