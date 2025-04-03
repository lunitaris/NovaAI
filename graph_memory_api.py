from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
from datetime import datetime
from CoreIA.graph_memory import get_graph_memory

# Créer un routeur FastAPI pour les endpoints de mémoire graphe
router = APIRouter(prefix="/memory/graph", tags=["graph-memory"])

# Modèles Pydantic pour la validation des données
class SummaryUpdate(BaseModel):
    field: str
    value: Any

class MessageCreate(BaseModel):
    role: str
    content: str
    session_id: Optional[str] = None

class SummaryCreate(BaseModel):
    theme: str
    summary: str
    importance: int = 5
    related_messages: Optional[List[str]] = None

# Obtenir le service de mémoire graphe
graph_memory = get_graph_memory()

# ========== Endpoints pour les messages ==========

@router.post("/messages", response_model=Dict[str, str])
async def create_message(message: MessageCreate):
    """Crée un nouveau message dans la mémoire graphe."""
    message_id = graph_memory.add_message(
        role=message.role, 
        content=message.content, 
        session_id=message.session_id
    )
    return {"status": "ok", "id": message_id}

@router.get("/messages/recent", response_model=Dict[str, Any])
async def get_recent_messages(limit: int = 10, session_id: Optional[str] = None):
    """Récupère les messages récents, optionnellement filtrés par session."""
    messages = graph_memory.get_recent_messages(limit=limit, session_id=session_id)
    return {"status": "ok", "messages": messages}

@router.delete("/messages/{message_id}", response_model=Dict[str, str])
async def delete_message(message_id: str):
    """Supprime un message de la mémoire graphe."""
    success = graph_memory.delete_message(message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    return {"status": "ok"}

@router.get("/search", response_model=Dict[str, Any])
async def search_similar_messages(
    q: str = Query(..., description="Texte à rechercher"),
    k: int = Query(5, description="Nombre de résultats à retourner"),
    min_similarity: float = Query(0.6, description="Score minimal de similarité")
):
    """Recherche les messages sémantiquement similaires à une requête."""
    results = graph_memory.search_similar(query=q, k=k, min_similarity=min_similarity)
    return {"status": "ok", "results": results}

# ========== Endpoints pour les résumés ==========

@router.post("/summaries", response_model=Dict[str, str])
async def create_summary(summary: SummaryCreate):
    """Crée un nouveau résumé thématique."""
    summary_id = graph_memory.add_summary(
        theme=summary.theme,
        summary=summary.summary,
        importance=summary.importance,
        related_messages=summary.related_messages
    )
    return {"status": "ok", "id": summary_id}

@router.get("/summaries", response_model=Dict[str, Any])
async def get_summaries(
    theme: Optional[str] = None,
    limit: int = Query(10, description="Nombre de résumés à retourner")
):
    """Récupère les résumés thématiques, optionnellement filtrés par thème."""
    summaries = graph_memory.get_summaries(theme=theme, limit=limit)
    return {"status": "ok", "summaries": summaries}

@router.delete("/summaries/{summary_id}", response_model=Dict[str, str])
async def delete_summary(summary_id: str):
    """Supprime un résumé thématique."""
    success = graph_memory.delete_summary(summary_id)
    if not success:
        raise HTTPException(status_code=404, detail="Résumé non trouvé")
    return {"status": "ok"}

@router.patch("/summaries/{summary_id}", response_model=Dict[str, Any])
async def update_summary(summary_id: str, update: SummaryUpdate):
    """Met à jour un champ d'un résumé."""
    if update.field not in {"theme", "importance", "content"}:
        raise HTTPException(status_code=400, detail="Champ non autorisé")
    
    success = graph_memory.update_summary(
        summary_id=summary_id,
        field=update.field,
        value=update.value
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Résumé non trouvé")
    
    return {"status": "ok", "updated": {update.field: update.value}}

@router.post("/prune", response_model=Dict[str, int])
async def prune_summaries(
    max_age_days: int = Query(7, description="Âge maximal en jours"),
    min_importance: int = Query(3, description="Importance minimale")
):
    """Supprime les résumés trop anciens et peu importants."""
    deleted = graph_memory.prune_summaries(
        max_age_days=max_age_days,
        min_importance=min_importance
    )
    return {"deleted": deleted}

# ========== Endpoints avancés de graphe ==========

@router.get("/conversation/{message_id}", response_model=Dict[str, Any])
async def get_conversation_chain(
    message_id: str,
    depth: int = Query(5, description="Profondeur de la conversation")
):
    """Récupère une chaîne de conversation complète à partir d'un message."""
    chain = graph_memory.get_conversation_chain(message_id=message_id, depth=depth)
    return {"status": "ok", "conversation": chain}

@router.get("/themes", response_model=Dict[str, Any])
async def find_related_themes(
    q: str = Query(..., description="Texte pour trouver les thèmes pertinents"),
    limit: int = Query(3, description="Nombre de thèmes à retourner")
):
    """Trouve les thèmes les plus pertinents à partir d'une requête."""
    themes = graph_memory.find_related_themes(query=q, limit=limit)
    return {"status": "ok", "themes": themes}

# ========== Endpoints d'import/export ==========

@router.get("/export", response_model=Dict[str, Any])
async def export_memory():
    """Exporte les données de mémoire pour sauvegarde."""
    with graph_memory.driver.session() as session:
        # Exporter les messages
        messages_result = session.run("""
            MATCH (m:Message)
            RETURN m
        """)
        messages = [dict(record["m"]) for record in messages_result]
        
        # Exporter les résumés
        summaries_result = session.run("""
            MATCH (s:Summary)
            RETURN s
        """)
        summaries = [dict(record["s"]) for record in summaries_result]
        
        # Exporter les relations
        relations_result = session.run("""
            MATCH (a)-[r]->(b)
            RETURN 
                id(a) AS source_id, 
                id(b) AS target_id, 
                type(r) AS relationship,
                a.id AS source_external_id,
                b.id AS target_external_id
        """)
        relations = [dict(record) for record in relations_result]
    
    export_data = {
        "messages": messages,
        "summaries": summaries,
        "relations": relations,
        "export_date": datetime.utcnow().isoformat()
    }
    
    return export_data

@router.post("/import", response_model=Dict[str, Any])
async def import_memory(file: UploadFile = File(...)):
    """Importe des données de mémoire depuis un fichier de sauvegarde."""
    contents = await file.read()
    data = json.loads(contents)
    
    if not all(k in data for k in ("messages", "summaries", "relations")):
        raise HTTPException(status_code=400, detail="Format de fichier d'import invalide")
    
    imported = {
        "messages": 0,
        "summaries": 0,
        "relations": 0
    }
    
    # Implémentation de l'import (à adapter selon les besoins spécifiques)
    # Cette implémentation est simplifiée et pourrait nécessiter plus de validation
    # et de gestion des conflits dans un environnement de production
    
    with graph_memory.driver.session() as session:
        # Importer les messages
        for msg in data["messages"]:
            if "id" in msg and "role" in msg and "content" in msg:
                # Vérifier si le message existe déjà
                exists = session.run("""
                    MATCH (m:Message {id: $id})
                    RETURN count(m) AS count
                """, id=msg["id"]).single()["count"] > 0
                
                if not exists:
                    session.run("""
                        CREATE (m:Message $props)
                    """, props=msg)
                    imported["messages"] += 1
        
        # Importer les résumés
        for summary in data["summaries"]:
            if "id" in summary and "theme" in summary and "content" in summary:
                # Vérifier si le résumé existe déjà
                exists = session.run("""
                    MATCH (s:Summary {id: $id})
                    RETURN count(s) AS count
                """, id=summary["id"]).single()["count"] > 0
                
                if not exists:
                    session.run("""
                        CREATE (s:Summary $props)
                    """, props=summary)
                    imported["summaries"] += 1
        
        # Importer les relations (simplifié)
        for rel in data["relations"]:
            if all(k in rel for k in ("source_external_id", "target_external_id", "relationship")):
                # Vérifier si la relation existe déjà (simplifié)
                session.run("""
                    MATCH (a {id: $source_id}), (b {id: $target_id})
                    WHERE NOT (a)-[:`$rel_type`]->(b)
                    CREATE (a)-[:`$rel_type`]->(b)
                """, 
                source_id=rel["source_external_id"], 
                target_id=rel["target_external_id"],
                rel_type=rel["relationship"])
                imported["relations"] += 1
    
    return {"status": "ok", "imported": imported}

# ========== Endpoints de statistiques ==========

@router.get("/stats", response_model=Dict[str, Any])
async def get_memory_stats():
    """Récupère des statistiques sur la mémoire graphe."""
    with graph_memory.driver.session() as session:
        # Nombre total de nœuds par type
        counts = session.run("""
            MATCH (n)
            RETURN labels(n)[0] AS type, count(n) AS count
        """)
        node_counts = {record["type"]: record["count"] for record in counts}
        
        # Statistiques des thèmes
        theme_stats = session.run("""
            MATCH (s:Summary)
            WITH s.theme AS theme, avg(s.importance) AS avg_importance, count(s) AS count
            RETURN theme, avg_importance, count
            ORDER BY avg_importance DESC
        """)
        themes = [
            {"theme": record["theme"], 
             "avg_importance": record["avg_importance"], 
             "count": record["count"]}
            for record in theme_stats
        ]
        
        # Relations entre messages (conversations)
        relation_stats = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS type, count(r) AS count
        """)
        relations = {record["type"]: record["count"] for record in relation_stats}
    
    return {
        "node_counts": node_counts,
        "themes": themes,
        "relations": relations
    }