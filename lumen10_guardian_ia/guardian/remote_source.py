import json

import httpx

from guardian.security import read_protected


class RemoteSourceClient:
    def __init__(self, environment, settings):
        self.environment = environment
        self.settings = settings
        self.remote = json.loads(environment["config"])["remote_environment_id"]

    def request(self, suffix, params=None):
        token = read_protected(self.settings.data / "source-keys" / (self.environment["id"] + ".key"))
        url = self.environment["target"].rstrip("/") + "/api/v1/projects/" + self.remote + "/source/" + suffix
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            response = client.get(url, params=params, headers={"Authorization": "Bearer " + token})
        if response.status_code != 200:
            raise ValueError("Conector de código recusou a leitura. Verifique licença, chave, validade e escopo.")
        if len(response.content) > 2_000_000:
            raise ValueError("Resposta de código excedeu o limite")
        return response.json()

    def context(self):
        manifest = self.request("manifest")
        files = {}
        remaining = 18000
        for item in manifest.get("files", [])[:80]:
            if item["bytes"] > remaining:
                continue
            result = self.request("file", {"path": item["path"]})
            content = result["content"]
            files[item["path"]] = content
            remaining -= len(content)
            if len(files) >= 8:
                break
        return {
            "status": "Conector autenticado, leitura somente, contexto limitado",
            "available_source_files": len(manifest.get("files", [])),
            "files": files,
        }
