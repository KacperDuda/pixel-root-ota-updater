from diagrams import Cluster, Diagram, Edge
from diagrams.gcp.devtools import Build, GCR, Scheduler
from diagrams.gcp.compute import Run
from diagrams.gcp.storage import GCS
from diagrams.gcp.operations import Monitoring
from diagrams.gcp.security import SecretManager
from diagrams.onprem.vcs import Github
from diagrams.generic.device import Mobile
from diagrams.onprem.network import Internet

# ZMIANA: "labelloc": "t" ustawia tytuł na górze.
graph_attr = {
    "fontsize": "25",   # Nieco większa czcionka tytułu
    "bgcolor": "white",
    "pad": "0.5",
    "nodesep": "0.6",
    "ranksep": "0.75",
    "splines": "spline",
    "labelloc": "t"     # Tytuł na górze (Top)
}

with Diagram("Pixel Auto-Patcher Architecture", show=False, graph_attr=graph_attr, direction="LR"):

    # ZMIANA: Tłumaczenie na angielski
    with Cluster("External World"):
        developer = Github("GitHub Repo")
        google_servers = Internet("Google Factory\nImages")
        user_phone = Mobile("Pixel 10")
        
        # Niewidoczne krawędzie ustalające pionowy porządek w klastrze
        developer - Edge(style="invis") - google_servers - Edge(style="invis") - user_phone

    with Cluster("Google Cloud Platform"):
        
        with Cluster("1. CI/CD"):
            builder = Build("Cloud Build")
            registry = GCR("Artifact Registry")

        with Cluster("2. Runtime (Hourly)"): # Tłumaczenie
            cron = Scheduler("Trigger")
            worker = Run("Pixel Automator")
            logs = Monitoring("Logs")

        with Cluster("3. Storage"):
            bucket = GCS("GCS Cache")
        
        with Cluster("4. Security"):
            secrets = SecretManager("Secrets")

    # --- RELACJE ---

    # ZMIANA: Dodanie minlen="2.5" do krawędzi łączących klastry, 
    # aby zwiększyć margines między "External World" a "GCP".

    # A. CI/CD - Orange
    # minlen="2.5" odpycha builder (GCP) od developera (External)
    developer >> Edge(label="Push", color="darkorange", fontcolor="darkorange", minlen="2.5") >> builder
    builder >> Edge(label="Build", color="darkorange", fontcolor="darkorange") >> registry
    
    # B. Trigger - Blue
    cron >> Edge(color="blue") >> worker
    registry >> Edge(label="Pull", color="blue", style="dashed", fontcolor="blue") >> worker

    # C. Worker Logic - English Labels
    
    # 1. Android Version check
    # minlen="2.5" dla powrotu do Google Servers (External)
    worker >> Edge(label="1. Android Ver.", minlen="2.5") >> google_servers
    
    # 2. Check Cache
    worker >> Edge(label="2. Check Hash", color="black", fontcolor="black") >> bucket
    
    # 3. Fetch Key - Red/Bold
    worker >> Edge(label="3. Fetch Key", color="red", style="bold", fontcolor="red") >> secrets
    
    # 4. Download - Dashed
    # minlen="2.5" dla powrotu do Google Servers (External)
    worker >> Edge(label="4. Download ZIP", style="dashed", color="gray", fontcolor="gray", minlen="2.5") >> google_servers
    
    # 5. Upload - Bold
    worker >> Edge(label="5. Upload .zip", style="bold") >> bucket

    # D. Monitoring
    worker >> Edge(color="gray") >> logs

    # E. User - Green
    # minlen="2.5" odpycha telefon (External) od bucketa (GCP)
    bucket >> Edge(label="Download Update", color="green", style="bold", fontcolor="darkgreen", minlen="2.5") >> user_phone

print("Diagram generated as pixel_auto_patcher_architecture_v2.png")