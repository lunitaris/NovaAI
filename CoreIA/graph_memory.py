from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import numpy as np
import time
import logging
import uuid
from datetime import datetime
import json

logger = logging.getLogger("graph-memory")

class GraphMemoryService:
    """
    Service unifié de gestion de la mémoire de Nova basé sur Neo4j.
    Remplace les trois types de mémoire précédents (volatile, sémantique, synthétique).
    """

    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password", 
                embedding_model="all-MiniLM-L6-v2"):
        """
        Initialise le service de mémoire graphe.
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.model = SentenceTransformer(embedding_model)
        
        # Déterminer la version de Neo4j pour utiliser la syntaxe appropriée
        with self.driver.session() as session:
            try:
                version_result = session.run("CALL dbms.components() YIELD versions RETURN versions[0] AS version")
                version_str = version_result.single()["version"]
                major_version = int(version_str.split('.')[0])
                
                # Utiliser la syntaxe appropriée selon la version
                if major_version >= 5:
                    # Syntaxe pour Neo4j 5.x et supérieur
                    session.run("CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE")
                    session.run("CREATE CONSTRAINT summary_id IF NOT EXISTS FOR (s:Summary) REQUIRE s.id IS UNIQUE")
                    
                    # Index pour les recherches temporelles
                    session.run("CREATE INDEX message_timestamp IF NOT EXISTS FOR (m:Message) ON (m.timestamp)")
                    session.run("CREATE INDEX summary_timestamp IF NOT EXISTS FOR (s:Summary) ON (s.timestamp)")
                    session.run("CREATE INDEX summary_theme IF NOT EXISTS FOR (s:Summary) ON (s.theme)")
                else:
                    # Syntaxe pour Neo4j 4.x et inférieur
                    session.run("CREATE CONSTRAINT message_id IF NOT EXISTS ON (m:Message) ASSERT m.id IS UNIQUE")
                    session.run("CREATE CONSTRAINT summary_id IF NOT EXISTS ON (s:Summary) ASSERT s.id IS UNIQUE")
                    
                    # Index pour les recherches temporelles
                    session.run("CREATE INDEX message_timestamp IF NOT EXISTS FOR (m:Message) ON (m.timestamp)")
                    session.run("CREATE INDEX summary_timestamp IF NOT EXISTS FOR (s:Summary) ON (s.timestamp)")
                    session.run("CREATE INDEX summary_theme IF NOT EXISTS FOR (s:Summary) ON (s.theme)")
                    
            except Exception as e:
                print(f"⚠️ Erreur lors de la création des contraintes: {e}")
                print("⚠️ Utilisation de la syntaxe Neo4j 5.x par défaut")
                
                # Utiliser la syntaxe Neo4j 5.x par défaut en cas d'erreur
                try:
                    session.run("CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE")
                    session.run("CREATE CONSTRAINT summary_id IF NOT EXISTS FOR (s:Summary) REQUIRE s.id IS UNIQUE")
                    
                    # Index pour les recherches temporelles
                    session.run("CREATE INDEX message_timestamp IF NOT EXISTS FOR (m:Message) ON (m.timestamp)")
                    session.run("CREATE INDEX summary_timestamp IF NOT EXISTS FOR (s:Summary) ON (s.timestamp)")
                    session.run("CREATE INDEX summary_theme IF NOT EXISTS FOR (s:Summary) ON (s.theme)")
                except Exception as e2:
                    print(f"⚠️ Échec de la création des contraintes: {e2}")
                    print("⚠️ Les contraintes et index ne sont pas créés")



    def close(self):
        """Ferme proprement la connexion à Neo4j"""
        self.driver.close()
    
    # ========== Fonctions remplaçant ShortTermMemory ==========
    
    def add_message(self, role, content, session_id=None):
        """
        Ajoute un message à la mémoire (équivalent volatile_memory.add).
        
        :param role: "user" ou "assistant"
        :param content: Contenu du message
        :param session_id: Identifiant optionnel de session
        :return: ID du message créé
        """
        message_id = str(uuid.uuid4())
        embedding = self.model.encode(content).tolist()  # Convertir numpy array en liste
        timestamp = datetime.utcnow().isoformat()
        
        with self.driver.session() as session:
            # Trouver le dernier message pour établir une relation REPLIED_TO
            last_message = session.run("""
                MATCH (m:Message)
                WHERE m.session_id = $session_id
                RETURN m.id AS id
                ORDER BY m.timestamp DESC
                LIMIT 1
            """, session_id=session_id).single()
            
            # Créer le nouveau message
            session.run("""
                CREATE (m:Message {
                    id: $id,
                    role: $role,
                    content: $content,
                    embedding: $embedding,
                    timestamp: $timestamp,
                    session_id: $session_id
                })
            """, id=message_id, role=role, content=content, 
                 embedding=embedding, timestamp=timestamp, session_id=session_id)
            
            # Si c'est une réponse, créer la relation
            if last_message and role == "assistant":
                session.run("""
                    MATCH (prev:Message {id: $prev_id})
                    MATCH (curr:Message {id: $curr_id})
                    CREATE (curr)-[:REPLIED_TO]->(prev)
                """, prev_id=last_message["id"], curr_id=message_id)
        
        return message_id
    
    def get_recent_messages(self, limit=6, session_id=None):
        """
        Récupère les messages récents (équivalent volatile_memory.get).
        
        :param limit: Nombre maximum de messages à récupérer
        :param session_id: Filtre optionnel par session
        :return: Liste de dictionnaires {role, content}
        """
        with self.driver.session() as session:
            query = """
                MATCH (m:Message)
                WHERE m.session_id = $session_id
                RETURN m.role AS role, m.content AS content, m.timestamp AS timestamp
                ORDER BY m.timestamp DESC
                LIMIT $limit
            """ if session_id else """
                MATCH (m:Message)
                RETURN m.role AS role, m.content AS content, m.timestamp AS timestamp
                ORDER BY m.timestamp DESC
                LIMIT $limit
            """
            
            result = session.run(query, session_id=session_id, limit=limit)
            messages = [{"role": record["role"], "content": record["content"]} 
                       for record in result]
            
            # Inverser pour obtenir l'ordre chronologique
            return list(reversed(messages))
    
    # ========== Fonctions remplaçant SemanticMemory ==========

    def search_similar(self, query, k=3, min_similarity=0.6):
        """
        Recherche les messages sémantiquement similaires.
        Version simplifiée sans utiliser gds.similarity.cosine
        """
        query_embedding = self.model.encode(query).tolist()
        
        with self.driver.session() as session:
            try:
                # Version simplifiée sans similarité vectorielle
                result = session.run("""
                    MATCH (m:Message)
                    RETURN m.id AS id, 
                        m.role AS role, 
                        m.content AS user, 
                        m.content AS assistant
                    LIMIT $k
                """, k=k)
                
                messages = []
                
                for record in result:
                    messages.append({
                        "user": record["user"] or query,
                        "assistant": record["assistant"] or "Je n'ai pas de réponse pour cette question.",
                        "similarity": 0.7  # Valeur arbitraire en l'absence de calcul réel
                    })
                
                if not messages:
                    # Retourner des valeurs par défaut si aucun message n'est trouvé
                    messages = [{
                        "user": query,
                        "assistant": "Je n'ai pas encore de contexte pour cette question.",
                        "similarity": 0.5
                    }]
                
                return messages
                    
            except Exception as e:
                logger.warning(f"Message search failed: {e}")
                
                # Retourner une liste vide en cas d'échec
                return [{
                    "user": query,
                    "assistant": "Je n'ai pas encore de contexte pour cette question.",
                    "similarity": 0.5
                }]

    def delete_message(self, message_id):
        """
        Supprime un message et ses relations (équivalent semantic_memory.delete_by_id).
        
        :param message_id: ID du message à supprimer
        :return: True si supprimé, False sinon
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Message {id: $id})
                DETACH DELETE m
                RETURN count(m) AS deleted
            """, id=message_id)
            
            return result.single()["deleted"] > 0
    
    # ========== Fonctions remplaçant SyntheticMemory ==========
    
    def add_summary(self, theme, summary, importance=5, related_messages=None):
        """
        Ajoute un résumé thématique (équivalent synthetic_memory.add_summary).
        
        :param theme: Thème du résumé
        :param summary: Contenu du résumé
        :param importance: Score d'importance (1-10)
        :param related_messages: Liste optionnelle d'IDs de messages liés à ce résumé
        :return: ID du résumé créé
        """
        summary_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        embedding = self.model.encode(summary).tolist()
        
        with self.driver.session() as session:
            # Créer le nœud résumé
            session.run("""
                CREATE (s:Summary {
                    id: $id,
                    theme: $theme,
                    content: $summary,
                    importance: $importance,
                    timestamp: $timestamp,
                    embedding: $embedding
                })
            """, id=summary_id, theme=theme, summary=summary, 
                 importance=importance, timestamp=timestamp, embedding=embedding)
            
            # Lier aux messages concernés si spécifiés
            if related_messages:
                for msg_id in related_messages:
                    session.run("""
                        MATCH (m:Message {id: $msg_id})
                        MATCH (s:Summary {id: $summary_id})
                        CREATE (s)-[:RELATES_TO]->(m)
                    """, msg_id=msg_id, summary_id=summary_id)
        
        return summary_id
    
    def get_summaries(self, theme=None, limit=10):
        """
        Récupère les résumés, optionnellement filtrés par thème (équivalent synthetic_memory.get_summaries).
        
        :param theme: Thème optionnel pour filtrer les résumés
        :param limit: Nombre maximum de résumés à récupérer
        :return: Liste de dictionnaires contenant les résumés
        """
        with self.driver.session() as session:
            query = """
                MATCH (s:Summary)
                WHERE s.theme = $theme
                RETURN s.id AS id, s.theme AS theme, s.content AS summary, 
                       s.importance AS importance, s.timestamp AS timestamp
                ORDER BY s.importance DESC
                LIMIT $limit
            """ if theme else """
                MATCH (s:Summary)
                RETURN s.id AS id, s.theme AS theme, s.content AS summary, 
                       s.importance AS importance, s.timestamp AS timestamp
                ORDER BY s.importance DESC
                LIMIT $limit
            """
            
            result = session.run(query, theme=theme, limit=limit)
            return [dict(record) for record in result]
    
    def delete_summary(self, summary_id):
        """
        Supprime un résumé et ses relations (équivalent synthetic_memory.delete_summary).
        
        :param summary_id: ID du résumé à supprimer
        :return: True si supprimé, False sinon
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:Summary {id: $id})
                DETACH DELETE s
                RETURN count(s) AS deleted
            """, id=summary_id)
            
            return result.single()["deleted"] > 0
    
    def update_summary(self, summary_id, field, value):
        """
        Met à jour un champ d'un résumé (équivalent PATCH /memory/synthetic/{summary_id}).
        
        :param summary_id: ID du résumé à mettre à jour
        :param field: Champ à modifier (theme, importance, content)
        :param value: Nouvelle valeur
        :return: True si mis à jour, False sinon
        """
        allowed_fields = {"theme", "importance", "content"}
        if field not in allowed_fields:
            return False
        
        with self.driver.session() as session:
            if field == "importance":
                try:
                    value = int(value)
                except ValueError:
                    return False
            
            # Utiliser des paramètres dynamiques pour le champ à mettre à jour
            query = f"""
                MATCH (s:Summary {{id: $id}})
                SET s.{field} = $value
                RETURN count(s) AS updated
            """
            
            result = session.run(query, id=summary_id, value=value)
            return result.single()["updated"] > 0
    
    def prune_summaries(self, max_age_days=7, min_importance=3):
        """
        Supprime les résumés trop anciens et peu importants (équivalent synthetic_memory.prune).
        
        :param max_age_days: Âge maximal (en jours) des résumés peu importants
        :param min_importance: Seuil d'importance minimal pour conserver sans limite de temps
        :return: Nombre de résumés supprimés
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:Summary)
                WHERE s.importance < $min_importance AND s.timestamp < $cutoff_date
                WITH s
                DETACH DELETE s
                RETURN count(s) AS deleted
            """, min_importance=min_importance, cutoff_date=cutoff_date)
            
            return result.single()["deleted"]
    
    # ========== Fonctions avancées de graphe ==========
    
    def get_conversation_chain(self, message_id, depth=5):
        """
        Récupère une chaîne de conversation complète à partir d'un message.
        
        :param message_id: ID du message de départ
        :param depth: Profondeur maximale de la chaîne à explorer
        :return: Liste de messages formant la conversation
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = (m:Message {id: $id})-[:REPLIED_TO*0..5]-(related)
                RETURN related.role AS role, related.content AS content, related.timestamp AS timestamp
                ORDER BY related.timestamp
            """, id=message_id)
            
            return [{"role": record["role"], "content": record["content"]} 
                   for record in result]


    def find_related_themes(self, query, limit=3):
        """
        Trouve les thèmes les plus pertinents à partir d'une requête.
        """
        query_embedding = self.model.encode(query).tolist()
        
        with self.driver.session() as session:
            try:
                # Version simplifiée sans gds.similarity.cosine
                result = session.run("""
                    MATCH (s:Summary)
                    RETURN s.theme AS theme, count(*) AS count
                    ORDER BY count DESC
                    LIMIT $limit
                """, limit=limit)
                
                return [{"theme": record["theme"] or "général", 
                        "relevance": 1.0,
                        "count": record["count"]} for record in result]
                    
            except Exception as e:
                logger.warning(f"Vector theme search failed, using simpler approach: {e}")
                
                # Très simple, juste pour démarrer
                result = session.run("""
                    MATCH (s:Summary)
                    RETURN DISTINCT s.theme AS theme
                    LIMIT $limit
                """, limit=limit)
                
                themes = [{"theme": record["theme"] or "général", 
                        "relevance": 1.0,
                        "count": 1} for record in result]
                        
                # Si aucun thème n'est trouvé, fournir un thème par défaut
                if not themes:
                    themes = [{"theme": "général", "relevance": 1.0, "count": 0}]
                    
                return themes



    def prepare_conversation_context(self, user_message, session_id=None, k_similar=3, k_summaries=2):
        """
        Prépare le contexte complet pour une nouvelle conversation.
        Combine les fonctionnalités des trois types de mémoire précédents.
        
        :param user_message: Message de l'utilisateur 
        :param session_id: ID de session optionnel
        :param k_similar: Nombre de souvenirs similaires à inclure
        :param k_summaries: Nombre de résumés à inclure
        :return: Liste de messages formatés pour le LLM
        """
        # Structure finale à construire
        conversation = []
        
        # 1. Charger le prompt système (comme dans chat_engine.py)
        try:
            with open("CoreIA/personality.json", "r", encoding="utf-8") as f:
                system_prompt = json.load(f)
                conversation.append(system_prompt)
        except Exception as e:
            logger.warning(f"Couldn't load personality: {e}")
            conversation.append({"role": "system", "content": "You are a helpful assistant."})
        
        # 2. Récupérer les messages récents (remplace ShortTermMemory)
        recent_messages = self.get_recent_messages(limit=6, session_id=session_id)
        conversation.extend(recent_messages)
        
        # 3. Rechercher des interactions similaires (remplace SemanticMemory)
        similar_memories = self.search_similar(user_message, k=k_similar)
        for item in similar_memories:
            # Insérer après le prompt système, comme dans l'original
            conversation.insert(1, {"role": "assistant", "content": item["assistant"]})
        
        # 4. Récupérer les résumés synthétiques pertinents (remplace SyntheticMemory)
        related_themes = self.find_related_themes(user_message, limit=2)
        summaries = []
        
        # Parcourir chaque thème et récupérer ses résumés
        for theme_info in related_themes:
            theme_summaries = self.get_summaries(theme=theme_info["theme"], limit=1)
            summaries.extend(theme_summaries)
        
        # Si nous n'avons pas assez de résumés thématiques, ajouter les plus importants
        if len(summaries) < k_summaries:
            general_summaries = self.get_summaries(limit=k_summaries - len(summaries))
            summaries.extend(general_summaries)
        
        # Limiter et ajouter au contexte
        for entry in summaries[:k_summaries]:
            conversation.insert(1, {
                "role": "assistant", 
                "content": f"[Summarized context]: {entry['summary']}"
            })
        
        # 5. Ajouter le message actuel de l'utilisateur
        conversation.append({"role": "user", "content": user_message})
        
        return conversation

# Fonction utilitaire pour obtenir une instance singleton
_graph_memory_instance = None

def get_graph_memory():
    global _graph_memory_instance
    if _graph_memory_instance is None:
        _graph_memory_instance = GraphMemoryService()
    return _graph_memory_instance