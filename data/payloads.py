def conciliar (changes: dict, comment: str = "Ajuste de prueba") -> dict:
    return {"comment":comment, "changes":changes}

def flow_config (levels: int = 2, active: bool = True) -> dict:
    return {"levels":levels, "active":active}

def approvers_config (approvers: dict) -> dict:
    return {"level_1":approvers.get("level_1",[]), "level_2":approvers.get("level_2",[])}