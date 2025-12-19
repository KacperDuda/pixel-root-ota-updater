from diagrams import Cluster, Diagram, Edge
from diagrams.gcp.devtools import Build, GCR, Scheduler
from diagrams.gcp.compute import Run
from diagrams.gcp.storage import GCS
from diagrams.gcp.operations import Monitoring
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

with Diagram("Pixel Auto-Patcher Architecture", show=False, graph_attr=graph_attr, direction="LR"):
    with Cluster("External World"):
        developer = Github("GitHub Repo")
        google_servers = Internet("Google Factory\nImages")
        user_phone = Mobile("Pixel 10")
        
        developer - Edge(style="invis") - google_servers - Edge(style="invis") - user_phone

    with Cluster("Google Cloud Platform"):
        with Cluster("1. CI/CD"):
            builder = Build("Cloud Build")
            registry = GCR("Artifact Registry")

        with Cluster("2. Runtime (Hourly)"):
            cron = Scheduler("Trigger")
            worker = Run("Pixel Automator")
            logs = Monitoring("Logs")

        with Cluster("3. Storage"):
            bucket = GCS("GCS Cache")
        
        with Cluster("4. Security"):
            secrets = SecretManager("Secrets")

    developer >> Edge(label="Push", color="darkorange", fontcolor="darkorange", minlen="2.5") >> builder
    builder >> Edge(label="Build", color="darkorange", fontcolor="darkorange") >> registry
    
    cron >> Edge(color="blue") >> worker
    registry >> Edge(label="Pull", color="blue", style="dashed", fontcolor="blue") >> worker

    worker >> Edge(label="1. Android Ver.", minlen="2.5") >> google_servers
    worker >> Edge(label="2. Check Hash", color="black", fontcolor="black") >> bucket
    worker >> Edge(label="3. Fetch Key", color="red", style="bold", fontcolor="red") >> secrets
    worker >> Edge(label="4. Download ZIP", style="dashed", color="gray", fontcolor="gray", minlen="2.5") >> google_servers
    worker >> Edge(label="5. Upload .zip", style="bold") >> bucket

    worker >> Edge(color="gray") >> logs
    bucket >> Edge(label="Download Update", color="green", style="bold", fontcolor="darkgreen", minlen="2.5") >> user_phone

print("Diagram generated as pixel_auto_patcher_architecture_v2.png")