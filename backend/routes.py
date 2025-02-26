from . import app
import os
import json
import pymongo
from flask import jsonify, request, make_response, abort, url_for  # noqa; F401
from pymongo import MongoClient
from bson import json_util
from pymongo.errors import OperationFailure
from pymongo.results import InsertOneResult
from bson.objectid import ObjectId
import sys

# Variables de configuration MongoDB
SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
json_url = os.path.join(SITE_ROOT, "data", "songs.json")
songs_list: list = json.load(open(json_url))

# Récupérer les variables d'environnement pour MongoDB
mongodb_service = os.environ.get('MONGODB_SERVICE', 'localhost')  # Par défaut localhost
mongodb_username = os.environ.get('MONGODB_USERNAME', '')
mongodb_password = os.environ.get('MONGODB_PASSWORD', '')
mongodb_port = os.environ.get('MONGODB_PORT', '27017')  # Port par défaut MongoDB

print(f'The value of MONGODB_SERVICE is: {mongodb_service}')

# Vérification si le service MongoDB est défini
if mongodb_service is None:
    app.logger.error('Missing MongoDB server in the MONGODB_SERVICE variable')
    sys.exit(1)

# Création de l'URL de connexion MongoDB
if mongodb_username and mongodb_password:
    url = f"mongodb://{mongodb_username}:{mongodb_password}@{mongodb_service}:{mongodb_port}"
else:
    url = f"mongodb://{mongodb_service}:{mongodb_port}"

print(f"Connecting to MongoDB at: {url}")

# Connexion à MongoDB
try:
    client = MongoClient(url)
    db = client.songs  # Accéder à la base de données "songs"
    db.songs.drop()  # Supprimer toutes les chansons existantes avant de les insérer
    db.songs.insert_many(songs_list)  # Insérer la liste des chansons
    print(f"Successfully connected to MongoDB at {mongodb_service}")
except OperationFailure as e:
    app.logger.error(f"Authentication error: {str(e)}")
    sys.exit(1)
except pymongo.errors.ConnectionError as e:
    app.logger.error(f"Connection error: {str(e)}")
    sys.exit(1)

# Fonction pour formater les données MongoDB en JSON
def parse_json(data):
    return json.loads(json_util.dumps(data))

######################################################################
# Implémentation des points de terminaison

# Point de terminaison /health
@app.route("/health", methods=["GET"])
def health():
    """Point de terminaison pour vérifier l'état du serveur."""
    return jsonify({"status": "OK"}), 200

# Point de terminaison /count
@app.route("/count", methods=["GET"])
def count():
    """Retourner le nombre total de chansons dans la base de données"""
    count = db.songs.count_documents({})  # Compte tous les documents dans la collection "songs"
    return jsonify({"count": count}), 200

# Point de terminaison pour récupérer toutes les chansons
@app.route("/song", methods=["GET"])
def get_songs():
    """Retourner toutes les chansons"""
    songs = db.songs.find()  # Récupérer toutes les chansons de MongoDB
    song_list = [parse_json(song) for song in songs]  # Convertir chaque chanson en JSON
    return jsonify({"songs": song_list}), 200


# Point de terminaison pour récupérer une chanson spécifique par son ID
@app.route("/song/<int:id>", methods=["GET"])
def get_song_by_id(id):
    # Recherche de la chanson par ID dans MongoDB
    song = db.songs.find_one({"id": id})  # Chercher par "id"
    
    # Si la chanson n'est pas trouvée, renvoyer une erreur 404
    if song is None:
        return jsonify({"message": "Chanson avec cet id non trouvée"}), 404
    
    # Utilisez json_util.dumps pour sérialiser le BSON (incluant l'ObjectId)
    song_json = json_util.dumps(song)
    
    # Retournez la chanson sous forme de JSON avec un statut HTTP 200
    return song_json, 200


# Point de terminaison pour ajouter une nouvelle chanson
@app.route("/song", methods=["POST"])
def create_song():
    # Extraire les données envoyées dans le corps de la requête
    song_data = request.get_json()

    # Vérifier si l'ID de la chanson existe déjà dans la base de données
    existing_song = db.songs.find_one({"id": song_data["id"]})
    
    if existing_song:
        # Si la chanson existe déjà, renvoyer un message d'erreur avec un code HTTP 302
        return jsonify({"Message": f"Song with id {song_data['id']} already present"}), 302
    
    # Si la chanson n'existe pas, insérer la nouvelle chanson dans la base de données
    result = db.songs.insert_one(song_data)

    # Retourner l'ID de la chanson insérée et un code HTTP 201 (Créé)
    # Format du JSON attendu : {"inserted id": {"$oid": "ID_INSÉRÉ"}}
    response = {
        "inserted id": {
            "$oid": str(result.inserted_id)  # Convertir l'ID en chaîne de caractères
        }
    }
    
    return jsonify(response), 201  # Code 201 pour création réussie


# Point de terminaison pour mettre à jour une chanson
@app.route("/song/<int:id>", methods=["PUT"])
def update_song(id):
    # Votre logique pour mettre à jour la chanson ici
    try:
        # Extraire les données de la chanson du corps de la requête
        song_data = request.get_json()

        # Trouver la chanson par ID
        existing_song = db.songs.find_one({"id": id})

        if not existing_song:
            # Si la chanson n'existe pas, retourner une erreur 404
            return jsonify({"message": "Song not found"}), 404

        # Mettre à jour la chanson avec les nouvelles données
        updated_song = db.songs.update_one(
            {"id": id},  # Recherche de la chanson par ID
            {"$set": song_data}  # Mise à jour des données de la chanson
        )

        if updated_song.matched_count > 0:
            # Si une chanson a été trouvée et mise à jour
            updated_song_data = db.songs.find_one({"id": id})  # Récupérer les données mises à jour
            # Convertir l'ObjectId en chaîne de caractères pour le JSON
            updated_song_data["_id"] = str(updated_song_data["_id"])

            return jsonify({
                "_id": updated_song_data["_id"],
                "id": updated_song_data["id"],
                "lyrics": updated_song_data["lyrics"],
                "title": updated_song_data["title"]
            }), 201  # Retourne un code HTTP 201 (Created)
        else:
            # Si aucune chanson n'a été mise à jour (même ID mais données identiques)
            return jsonify({"message": "Song found, but nothing updated"}), 200

    except Exception as e:
        return jsonify({"message": "Internal server error", "error": str(e)}), 500


# Point de terminaison pour supprimer une chanson
@app.route("/song/<int:id>", methods=["DELETE"])
def delete_song(id):
    # Supprimer la chanson de la base de données en utilisant l'id
    result = db.songs.delete_one({"id": id})

    if result.deleted_count == 0:
        # Si aucune chanson n'a été supprimée, renvoyer un message d'erreur 404
        return jsonify({"message": "Song not found"}), 404

    # Si la chanson a été supprimée avec succès, renvoyer un statut HTTP 204 sans contenu
    return '', 204