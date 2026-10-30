import os
import sys
import tempfile
from pathlib import Path

# Environnement de test isolé (exécuté automatiquement par pytest avant les tests)
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["AGENT_API_KEY"] = "cle-api-de-test-1234567890"
os.environ["ADMIN_TOKEN"] = "jeton-admin-de-test-1234567890"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
