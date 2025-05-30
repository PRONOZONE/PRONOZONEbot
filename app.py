import os
import csv
import json 
from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime, date, timedelta, timezone
import logging
import uuid 
import time 
from collections import defaultdict
from dotenv import load_dotenv 

# --- Configuration des chemins des fichiers CSV ---
# Définir BASE_DIR avant son utilisation
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Charger les variables d'environnement au début
# S'assurer que le fichier .env est à la racine du dossier backend/ ou ajuster le chemin
# Si app.py est à la racine de PRONOZONEbot, alors .env doit aussi y être, ou le chemin doit être ajusté.
# Pour la structure actuelle où app.py est à la racine de PRONOZONEbot/ et .env serait dans PRONOZONEbot/backend/
# il faudrait faire: load_dotenv(os.path.join(BASE_DIR, 'backend', '.env'))
# Mais si .env est au même niveau que app.py, alors os.path.join(BASE_DIR, '.env') est correct.
# Supposons que .env est au même niveau que app.py pour l'instant.
dotenv_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    logging.info(f"Variables d'environnement chargées depuis {dotenv_path}")
else:
    # Essayer de charger depuis un dossier backend/ si app.py est à la racine du projet global
    dotenv_path_backend = os.path.join(BASE_DIR, 'backend', '.env')
    if os.path.exists(dotenv_path_backend):
        load_dotenv(dotenv_path_backend)
        logging.info(f"Variables d'environnement chargées depuis {dotenv_path_backend}")
    else:
        logging.warning("Fichier .env non trouvé à la racine ou dans backend/. Les variables d'environnement système seront utilisées si définies.")


# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Utiliser BASE_DIR pour les autres chemins de fichiers
USERS_FILE = os.path.join(BASE_DIR, 'users.csv')
MATCHES_FILE = os.path.join(BASE_DIR, 'matches.csv')
PARIS_FILE = os.path.join(BASE_DIR, 'paris.csv')
SUIVIS_FILE = os.path.join(BASE_DIR, 'suivis.csv')

# --- Définition des en-têtes pour les fichiers CSV ---
USERS_HEADER = ['user_id', 'pseudo', 'join_date', 'xp', 'level', 'email', 'pronocoins_balance', 
                'last_daily_reward_date', 'tutorial_completed_reward_claimed', 
                'google_linked_reward_claimed', 'pseudo_created_reward_claimed', 
                'unlocked_pronos', 'bet_count', 'three_bets_reward_claimed',
                'tiktok_follow_reward_claimed', 'x_follow_reward_claimed', 
                'instagram_follow_reward_claimed', 'telegram_channel_reward_claimed',
                'telegram_chat_reward_claimed', 
                'last_ad_reward_timestamp',
                'telegram_first_name', 'telegram_last_name', 'telegram_username' 
                ]
MATCHES_HEADER = ['Date', 'Heure', 'Match', 'Pari', 'Cote', 'Risque', 'Note', 'Niveau', 'Statut', 'MatchID']
PARIS_HEADER = ['bet_id', 'user_id', 'MatchID', 'MatchName', 'DatePari', 'Montant', 'StatutPari', 
                'CotePari', 'BetType', 'CoteGagnante', 'Gain']
SUIVIS_HEADER = ['user_id', 'MatchID', 'date_suivi']

# --- Constantes de Gamification ---
PRONOCOINS_INITIAL_BALANCE = 50
PRONOCOINS_UNLOCK_COST = 10
PRONOCOINS_BET_COST = 10 
PRONOCOINS_DAILY_REWARD = 5
PRONOCOINS_AD_REWARD = 1 
XP_PER_BET = 1
XP_PER_UNLOCK = 2
XP_PER_DAILY_REWARD = 5 
XP_PER_AD_WATCH = 1 
REWARD_SOCIAL_PC = 3
REWARD_SOCIAL_XP = 5
AD_REWARD_COOLDOWN_SECONDS = 3600 


TASKS_CONFIG = {
    'tutorial': {'name': 'Terminer le tutoriel', 'pc_reward': 1, 'xp_reward': 5, 'claimed_field': 'tutorial_completed_reward_claimed'},
    'google': {'name': 'Lier son compte Google', 'pc_reward': 5, 'xp_reward': 10, 'claimed_field': 'google_linked_reward_claimed'},
    'pseudo': {'name': 'Créer son pseudo', 'pc_reward': 2, 'xp_reward': 5, 'claimed_field': 'pseudo_created_reward_claimed'},
    'three_bets': {'name': 'Faire 3 paris', 'pc_reward': 10, 'xp_reward': 15, 'claimed_field': 'three_bets_reward_claimed', 'condition_bet_count': 3},
    'tiktok': {'name': 'Suivre sur TikTok', 'pc_reward': REWARD_SOCIAL_PC, 'xp_reward': REWARD_SOCIAL_XP, 'claimed_field': 'tiktok_follow_reward_claimed'},
    'x': {'name': 'Suivre sur X (Twitter)', 'pc_reward': REWARD_SOCIAL_PC, 'xp_reward': REWARD_SOCIAL_XP, 'claimed_field': 'x_follow_reward_claimed'},
    'instagram': {'name': 'Suivre sur Instagram', 'pc_reward': REWARD_SOCIAL_PC, 'xp_reward': REWARD_SOCIAL_XP, 'claimed_field': 'instagram_follow_reward_claimed'},
    'tg_channel': {'name': 'Rejoindre le Canal Telegram', 'pc_reward': REWARD_SOCIAL_PC, 'xp_reward': REWARD_SOCIAL_XP, 'claimed_field': 'telegram_channel_reward_claimed'},
    'tg_chat': {'name': 'Rejoindre le Chat Telegram', 'pc_reward': REWARD_SOCIAL_PC, 'xp_reward': REWARD_SOCIAL_XP, 'claimed_field': 'telegram_chat_reward_claimed'}
}
LEVELS_XP = [0, 100, 250, 500, 1000, 2000, 5000, 10000] 

# --- Cache pour matches.csv ---
matches_cache = None
matches_cache_timestamp = 0
MATCHES_CACHE_DURATION = 300 

# --- Fonctions Utilitaires pour les CSV ---
def initialize_csv(file_path, header):
    if not os.path.exists(file_path):
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(header)
            logging.info(f"Fichier {file_path} créé avec les en-têtes.")
        except IOError as e:
            logging.error(f"Erreur lors de la création du fichier {file_path}: {e}")

def read_csv_as_list_of_dicts(file_path, use_cache=False, cache_var_name=None, cache_ts_name=None, cache_duration=60):
    global matches_cache, matches_cache_timestamp 

    if use_cache:
        current_time = time.time()
        cache_to_use = None
        ts_to_use = 0
        if cache_var_name == "matches_cache":
            cache_to_use = matches_cache
            ts_to_use = matches_cache_timestamp
        
        if cache_to_use is not None and (current_time - ts_to_use) < cache_duration:
            logging.debug(f"Utilisation du cache pour {file_path}")
            return list(cache_to_use) 

    data = []
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
        if use_cache and cache_var_name == "matches_cache":
            matches_cache = list(data) 
            matches_cache_timestamp = time.time()
            logging.info(f"Cache pour {file_path} mis à jour.")
    except FileNotFoundError:
        logging.warning(f"Le fichier {file_path} n'a pas été trouvé.")
        if file_path == MATCHES_FILE: initialize_csv(file_path, MATCHES_HEADER)
        elif file_path == USERS_FILE: initialize_csv(file_path, USERS_HEADER)
        elif file_path == PARIS_FILE: initialize_csv(file_path, PARIS_HEADER)
        elif file_path == SUIVIS_FILE: initialize_csv(file_path, SUIVIS_HEADER)
    except Exception as e:
        logging.error(f"Erreur lors de la lecture de {file_path}: {e}")
    return data

def write_csv_from_list_of_dicts(file_path, data, header):
    try:
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
        if file_path == MATCHES_FILE:
            global matches_cache
            matches_cache = None 
            logging.info(f"Cache pour {MATCHES_FILE} invalidé après écriture.")
    except Exception as e:
        logging.error(f"Erreur lors de l'écriture dans {file_path}: {e}")

def append_to_csv(file_path, data_row_dict, header):
    try:
        file_exists_non_empty = os.path.exists(file_path) and os.path.getsize(file_path) > 0
        with open(file_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header, extrasaction='ignore')
            if not file_exists_non_empty:
                writer.writeheader()
            writer.writerow(data_row_dict)
    except Exception as e:
        logging.error(f"Erreur lors de l'ajout à {file_path}: {e}")

initialize_csv(USERS_FILE, USERS_HEADER)
initialize_csv(MATCHES_FILE, MATCHES_HEADER)
initialize_csv(PARIS_FILE, PARIS_HEADER)
initialize_csv(SUIVIS_FILE, SUIVIS_HEADER)

def _convert_user_types(user_dict):
    if not user_dict: return None
    user_dict['xp'] = int(user_dict.get('xp', 0))
    user_dict['level'] = int(user_dict.get('level', 1))
    user_dict['pronocoins_balance'] = int(user_dict.get('pronocoins_balance', 0))
    user_dict['bet_count'] = int(user_dict.get('bet_count', 0))
    user_dict['last_ad_reward_timestamp'] = float(user_dict.get('last_ad_reward_timestamp', 0.0)) 
    for task_id in TASKS_CONFIG: 
        claimed_field = TASKS_CONFIG[task_id]['claimed_field']
        user_dict[claimed_field] = user_dict.get(claimed_field, 'false').lower() == 'true'
    user_dict['unlocked_pronos'] = user_dict.get('unlocked_pronos', '').split(',') if user_dict.get('unlocked_pronos') else []
    return user_dict

def get_user(user_id):
    users = read_csv_as_list_of_dicts(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    return _convert_user_types(user)

def update_user_atomic(user_id, update_fn):
    users = read_csv_as_list_of_dicts(USERS_FILE)
    user_found_and_updated = False
    updated_users_list = []
    user_to_return = None

    for u_dict_str in users: 
        if u_dict_str['user_id'] == user_id:
            u_typed = _convert_user_types(u_dict_str.copy()) 
            if u_typed is None: 
                updated_users_list.append(u_dict_str)
                continue

            u_modified_typed = update_fn(u_typed) 
            user_to_return = u_modified_typed.copy()

            u_final_str_dict = {}
            for header_col in USERS_HEADER:
                if header_col == 'unlocked_pronos':
                    u_final_str_dict[header_col] = ','.join(filter(None, u_modified_typed.get(header_col, [])))
                elif any(cfg['claimed_field'] == header_col for cfg in TASKS_CONFIG.values()): 
                    u_final_str_dict[header_col] = str(u_modified_typed.get(header_col, False)).lower()
                elif header_col == 'last_ad_reward_timestamp':
                    u_final_str_dict[header_col] = str(u_modified_typed.get(header_col, 0.0))
                elif header_col in ['telegram_first_name', 'telegram_last_name', 'telegram_username', 'email', 'pseudo', 'last_daily_reward_date', 'join_date']:
                    u_final_str_dict[header_col] = u_modified_typed.get(header_col, '')
                elif header_col in u_modified_typed: 
                     u_final_str_dict[header_col] = str(u_modified_typed[header_col])
                else:
                    u_final_str_dict[header_col] = u_dict_str.get(header_col, '') 

            updated_users_list.append(u_final_str_dict)
            user_found_and_updated = True
        else:
            updated_users_list.append(u_dict_str)
    
    if user_found_and_updated:
        write_csv_from_list_of_dicts(USERS_FILE, updated_users_list, USERS_HEADER)
        return user_to_return 
    return None


def check_and_apply_level_up(user_data_dict):
    current_level = user_data_dict.get('level', 1)
    current_xp = user_data_dict.get('xp', 0)
    
    leveled_up_this_check = False
    
    while current_level < len(LEVELS_XP): 
        xp_for_next_level = LEVELS_XP[current_level] 
        if current_xp >= xp_for_next_level:
            current_level += 1
            reward_pc = current_level 
            user_data_dict['level'] = current_level
            user_data_dict['pronocoins_balance'] = user_data_dict.get('pronocoins_balance',0) + reward_pc
            leveled_up_this_check = True
            logging.info(f"User {user_data_dict['user_id']} leveled up to {current_level}. Rewarded {reward_pc} PC.")
        else:
            break 
            
    return user_data_dict, leveled_up_this_check


# --- Routes de l'Application ---
@app.route('/')
def index_route(): 
    api_url_base = os.getenv("MINI_APP_URL", request.url_root.rstrip('/'))
    if "MINI_APP_URL" not in os.environ:
        logging.warning(f"MINI_APP_URL non trouvée dans .env, utilisation de request.url_root: {api_url_base}")
    return render_template('index.html', api_base_url=api_url_base)

# --- API Routes ---
@app.route('/api/user_profile', methods=['GET'])
def get_user_profile_route():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id manquant"}), 400

    user_profile = get_user(user_id)

    if user_profile:
        tg_first_name_arg = request.args.get('tg_first_name')
        tg_last_name_arg = request.args.get('tg_last_name')
        tg_username_arg = request.args.get('tg_username')
        
        updates_needed = {}
        if tg_first_name_arg and user_profile.get('telegram_first_name') != tg_first_name_arg:
            updates_needed['telegram_first_name'] = tg_first_name_arg
        if tg_last_name_arg and user_profile.get('telegram_last_name') != tg_last_name_arg:
            updates_needed['telegram_last_name'] = tg_last_name_arg
        if tg_username_arg and user_profile.get('telegram_username') != tg_username_arg:
            updates_needed['telegram_username'] = tg_username_arg
        
        if updates_needed:
            def update_tg_info(user_p):
                user_p.update(updates_needed)
                return user_p
            updated_profile = update_user_atomic(user_id, update_tg_info)
            if updated_profile:
                logging.info(f"Informations Telegram mises à jour pour {user_id}")
                return jsonify(updated_profile) 
            else: 
                return jsonify({"error": "Erreur lors de la mise à jour des infos Telegram"}), 500
        
        return jsonify(user_profile)
    else:
        tg_first_name = request.args.get('tg_first_name', '')
        tg_last_name = request.args.get('tg_last_name', '')
        tg_username = request.args.get('tg_username', '')

        default_pseudo = f"User_{user_id[:6]}"
        if tg_username:
            default_pseudo = tg_username
        elif tg_first_name:
            default_pseudo = tg_first_name
            
        new_user_data_dict = {
            'user_id': user_id, 'pseudo': default_pseudo, 
            'join_date': date.today().isoformat(), 'xp': 0, 'level': 1, 'email': '', 
            'pronocoins_balance': PRONOCOINS_INITIAL_BALANCE, 'last_daily_reward_date': '',
            'unlocked_pronos': '', 'bet_count': 0,
            'last_ad_reward_timestamp': '0.0',
            'telegram_first_name': tg_first_name, 
            'telegram_last_name': tg_last_name,
            'telegram_username': tg_username
        }
        for task_id in TASKS_CONFIG:
            new_user_data_dict[TASKS_CONFIG[task_id]['claimed_field']] = 'false'
        
        if default_pseudo != f"User_{user_id[:6]}":
             new_user_data_dict[TASKS_CONFIG['pseudo']['claimed_field']] = 'true' 
            
        append_to_csv(USERS_FILE, new_user_data_dict, USERS_HEADER)
        logging.info(f"Nouvel utilisateur créé via API : {user_id} avec pseudo {default_pseudo}")
        return jsonify(_convert_user_types(new_user_data_dict)), 201

@app.route('/api/matchs_csv', methods=['GET'])
def get_matchs_csv_route():
    pronostics = read_csv_as_list_of_dicts(MATCHES_FILE, use_cache=True, cache_var_name="matches_cache", cache_ts_name="matches_cache_timestamp", cache_duration=MATCHES_CACHE_DURATION)
    date_filter = request.args.get('date') 

    if date_filter:
        try:
            datetime.strptime(date_filter, "%Y-%m-%d") 
            pronostics_a_venir = [p for p in pronostics if p.get('Statut', '').lower() == 'à venir' and p.get('Date') == date_filter]
        except ValueError:
            return jsonify({"error": "Format de date invalide. Utilisez AAAA-MM-JJ."}), 400
    else:
        pronostics_a_venir = [p for p in pronostics if p.get('Statut', '').lower() == 'à venir']
    
    pronostics_a_venir.sort(key=lambda x: (x.get('Date', 'zzzz'), x.get('Heure', '99:99'))) 
    return jsonify(pronostics_a_venir)

@app.route('/api/parier', methods=['POST'])
def post_parier_route():
    data = request.json
    user_id = data.get('user_id')
    match_id = data.get('match_id')
    
    if not all([user_id, match_id]):
        return jsonify({"error": "Données manquantes (user_id, match_id)"}), 400
    try:
        montant_pari = int(PRONOCOINS_BET_COST)
    except ValueError:
        return jsonify({"error": "Montant de pari invalide"}), 400

    def update_bet_logic(user_p):
        if user_p['pronocoins_balance'] < montant_pari:
            raise ValueError("Solde insuffisant") 

        pronostics = read_csv_as_list_of_dicts(MATCHES_FILE, use_cache=True, cache_var_name="matches_cache", cache_ts_name="matches_cache_timestamp", cache_duration=MATCHES_CACHE_DURATION)
        match_info = next((p for p in pronostics if p['MatchID'] == match_id and p.get('Statut', '').lower() == 'à venir'), None)
        if not match_info:
            raise ValueError("Match non trouvé ou non disponible")
        
        if match_id not in user_p.get('unlocked_pronos', []):
            raise ValueError("Pronostic non débloqué")

        user_p['pronocoins_balance'] -= montant_pari
        user_p['xp'] += XP_PER_BET
        user_p['bet_count'] += 1
        
        user_p, _ = check_and_apply_level_up(user_p)
        
        task_3bets_config = TASKS_CONFIG['three_bets']
        if user_p['bet_count'] >= task_3bets_config['condition_bet_count'] and not user_p[task_3bets_config['claimed_field']]:
            logging.info(f"Utilisateur {user_id} a accompli la tâche 'faire 3 paris'. Peut maintenant réclamer.")

        nouveau_pari = {
            'bet_id': str(uuid.uuid4()), 'user_id': user_id, 'MatchID': match_id,
            'MatchName': match_info.get('Match', 'N/A'), 'DatePari': datetime.now(timezone.utc).isoformat(), 
            'Montant': montant_pari, 'StatutPari': 'en_cours', 
            'CotePari': match_info.get('Cote', 'N/A'), 'BetType': match_info.get('Pari', 'N/A'),
            'CoteGagnante': '', 'Gain': 0
        }
        append_to_csv(PARIS_FILE, nouveau_pari, PARIS_HEADER)
        return user_p

    try:
        updated_user = update_user_atomic(user_id, update_bet_logic)
        if updated_user:
            logging.info(f"Pari de {montant_pari} PC placé par {user_id} sur {match_id}.")
            return jsonify({
                "message": "Pari placé avec succès!",
                "new_balance": updated_user['pronocoins_balance'],
                "new_xp": updated_user['xp'],
                "new_level": updated_user['level'],
                "bet_count": updated_user['bet_count']
            }), 200
        else:
            return jsonify({"error": "Utilisateur non trouvé lors de la mise à jour"}), 404
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 403 
    except Exception as e:
        logging.error(f"Erreur interne lors du pari pour {user_id} sur {match_id}: {e}")
        return jsonify({"error": "Erreur interne du serveur"}), 500


@app.route('/api/unlock_prono', methods=['POST'])
def unlock_prono_route():
    data = request.json
    user_id = data.get('user_id')
    match_id = data.get('match_id')

    if not all([user_id, match_id]):
        return jsonify({"error": "user_id ou match_id manquant"}), 400

    def update_unlock_logic(user_p):
        if match_id in user_p.get('unlocked_pronos', []):
            return user_p 

        if user_p['pronocoins_balance'] < PRONOCOINS_UNLOCK_COST:
            raise ValueError("Solde insuffisant")

        user_p['pronocoins_balance'] -= PRONOCOINS_UNLOCK_COST
        user_p['xp'] += XP_PER_UNLOCK
        if match_id not in user_p['unlocked_pronos']: 
             user_p['unlocked_pronos'].append(match_id)
        user_p, _ = check_and_apply_level_up(user_p)
        return user_p

    try:
        updated_user = update_user_atomic(user_id, update_unlock_logic)
        if updated_user:
            logging.info(f"Pronostic {match_id} débloqué par {user_id}.")
            return jsonify({
                "message": "Pronostic débloqué avec succès!",
                "new_balance": updated_user['pronocoins_balance'],
                "new_xp": updated_user['xp'],
                "new_level": updated_user['level'],
                "unlocked_pronos": updated_user['unlocked_pronos']
            }), 200
        else:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 403
    except Exception as e:
        logging.error(f"Erreur interne lors du déblocage pour {user_id} sur {match_id}: {e}")
        return jsonify({"error": "Erreur interne du serveur"}), 500

@app.route('/api/claim_daily_reward', methods=['POST'])
def claim_daily_reward_route():
    data = request.json
    user_id = data.get('user_id')
    if not user_id: return jsonify({"error": "user_id manquant"}), 400

    def update_daily_reward_logic(user_p):
        today_str = date.today().isoformat()
        if user_p.get('last_daily_reward_date') == today_str:
            raise ValueError("Récompense quotidienne déjà réclamée")

        user_p['pronocoins_balance'] += PRONOCOINS_DAILY_REWARD
        user_p['xp'] += XP_PER_DAILY_REWARD
        user_p['last_daily_reward_date'] = today_str
        user_p, _ = check_and_apply_level_up(user_p)
        return user_p
        
    try:
        updated_user = update_user_atomic(user_id, update_daily_reward_logic)
        if updated_user:
            logging.info(f"Récompense quotidienne réclamée par {user_id}.")
            return jsonify({
                "message": f"Récompense de {PRONOCOINS_DAILY_REWARD} PC et {XP_PER_DAILY_REWARD} XP réclamée!",
                "new_balance": updated_user['pronocoins_balance'],
                "new_xp": updated_user['xp'],
                "new_level": updated_user['level'],
                "last_daily_reward_date": updated_user['last_daily_reward_date']
            }), 200
        else:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
    except ValueError as ve: 
        return jsonify({"error": str(ve)}), 403
    except Exception as e:
        logging.error(f"Erreur interne lors de la réclamation de la récompense quotidienne pour {user_id}: {e}")
        return jsonify({"error": "Erreur interne du serveur"}), 500

@app.route('/api/claim_ad_reward', methods=['POST'])
def claim_ad_reward_route():
    data = request.json
    user_id = data.get('user_id')
    if not user_id: return jsonify({"error": "user_id manquant"}), 400

    def update_ad_reward_logic(user_p):
        current_timestamp = time.time()
        last_ad_timestamp = user_p.get('last_ad_reward_timestamp', 0.0)

        if (current_timestamp - last_ad_timestamp) < AD_REWARD_COOLDOWN_SECONDS:
            remaining_time = AD_REWARD_COOLDOWN_SECONDS - (current_timestamp - last_ad_timestamp)
            raise ValueError(f"Veuillez attendre encore {int(remaining_time // 60)} min {int(remaining_time % 60)} sec avant la prochaine récompense publicitaire.")

        user_p['pronocoins_balance'] += PRONOCOINS_AD_REWARD
        user_p['xp'] += XP_PER_AD_WATCH
        user_p['last_ad_reward_timestamp'] = current_timestamp 
        user_p, _ = check_and_apply_level_up(user_p)
        return user_p
        
    try:
        updated_user = update_user_atomic(user_id, update_ad_reward_logic)
        if updated_user:
            logging.info(f"Récompense publicitaire réclamée par {user_id}.")
            return jsonify({
                "message": f"Vous avez gagné {PRONOCOINS_AD_REWARD} PC et {XP_PER_AD_WATCH} XP pour avoir regardé la publicité !",
                "new_balance": updated_user['pronocoins_balance'],
                "new_xp": updated_user['xp'],
                "new_level": updated_user['level'],
                "last_ad_reward_timestamp": updated_user['last_ad_reward_timestamp'] 
            }), 200
        else:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
    except ValueError as ve: 
        return jsonify({"error": str(ve)}), 403 
    except Exception as e:
        logging.error(f"Erreur interne lors de la réclamation de la récompense publicitaire pour {user_id}: {e}")
        return jsonify({"error": "Erreur interne du serveur"}), 500


@app.route('/api/update_pseudo', methods=['POST'])
def update_pseudo_route():
    data = request.json
    user_id = data.get('user_id')
    new_pseudo = data.get('pseudo', '').strip()

    if not user_id: return jsonify({"error": "user_id manquant"}), 400
    if not new_pseudo or len(new_pseudo) < 3 or len(new_pseudo) > 20:
        return jsonify({"error": "Le pseudo doit contenir entre 3 et 20 caractères."}), 400
    
    message_response = "Pseudo mis à jour avec succès!"

    def update_pseudo_logic(user_p):
        nonlocal message_response 
        user_p['pseudo'] = new_pseudo
        
        task_info = TASKS_CONFIG['pseudo']
        claimed_field = task_info['claimed_field']
        if not user_p.get(claimed_field, False): 
            user_p[claimed_field] = True
            user_p['pronocoins_balance'] += task_info['pc_reward']
            user_p['xp'] += task_info['xp_reward']
            user_p, _ = check_and_apply_level_up(user_p)
            message_response = f"Pseudo mis à jour! Récompense '{task_info['pc_reward']} PC, {task_info['xp_reward']} XP' obtenue!"
        return user_p

    try:
        updated_user = update_user_atomic(user_id, update_pseudo_logic)
        if updated_user:
            logging.info(f"Pseudo mis à jour pour {user_id} en '{new_pseudo}'.")
            return jsonify({
                "message": message_response,
                "new_pseudo": updated_user['pseudo'],
                "new_balance": updated_user['pronocoins_balance'],
                "new_xp": updated_user['xp'],
                "new_level": updated_user['level']
            }), 200
        else:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
    except Exception as e:
        logging.error(f"Erreur interne lors de la mise à jour du pseudo pour {user_id}: {e}")
        return jsonify({"error": "Erreur interne du serveur"}), 500

@app.route('/api/link_google_account', methods=['POST'])
def link_google_account_route():
    data = request.json
    user_id = data.get('user_id')
        
    if not user_id: return jsonify({"error": "user_id manquant"}), 400

    message_response = "Compte Google lié (simulation)!"
    _user_for_email = get_user(user_id) 
    pseudo_for_email = _user_for_email.get('pseudo', user_id).split('@')[0].replace(' ', '').lower() if _user_for_email else user_id.split('_')[0]
    simulated_email = f"{pseudo_for_email}@pronobot.dev"


    def link_google_logic(user_p):
        nonlocal message_response, simulated_email
        if user_p.get('email'): 
            message_response = f"Compte déjà lié à {user_p['email']}."
            return user_p

        user_p['email'] = simulated_email
        task_info = TASKS_CONFIG['google']
        claimed_field = task_info['claimed_field']
        if not user_p.get(claimed_field, False):
            user_p[claimed_field] = True
            user_p['pronocoins_balance'] += task_info['pc_reward']
            user_p['xp'] += task_info['xp_reward']
            user_p, _ = check_and_apply_level_up(user_p)
            message_response = f"Compte Google lié à {simulated_email}! Récompense '{task_info['pc_reward']} PC, {task_info['xp_reward']} XP' obtenue!"
        return user_p

    try:
        updated_user = update_user_atomic(user_id, link_google_logic)
        if updated_user:
            logging.info(f"Liaison Google (simulée) pour {user_id} avec email {updated_user['email']}.")
            return jsonify({
                "message": message_response,
                "email": updated_user['email'],
                "new_balance": updated_user['pronocoins_balance'],
                "new_xp": updated_user['xp'],
                "new_level": updated_user['level']
            }), 200
        else:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
    except Exception as e:
        logging.error(f"Erreur interne lors de la liaison Google (simulée) pour {user_id}: {e}")
        return jsonify({"error": "Erreur interne du serveur"}), 500


@app.route('/api/tasks_status', methods=['GET'])
def get_tasks_status_route():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({"error": "user_id manquant"}), 400
    user_profile = get_user(user_id)
    if not user_profile: return jsonify({"error": "Utilisateur non trouvé"}), 404

    tasks_status_response = []
    for task_id, config in TASKS_CONFIG.items():
        is_claimed = user_profile.get(config['claimed_field'], False)
        is_claimable = not is_claimed 
        
        if task_id == 'three_bets' and user_profile.get('bet_count', 0) < config['condition_bet_count']:
            is_claimable = False 
        if task_id == 'google' and not user_profile.get('email'): 
            is_claimable = False
        if task_id == 'pseudo' and (not user_profile.get('pseudo') or user_profile.get('pseudo', '').startswith('User_')): 
            is_claimable = False
        
        tasks_status_response.append({
            "id": task_id,
            "name": config['name'],
            "pc_reward": config['pc_reward'],
            "xp_reward": config['xp_reward'],
            "is_claimed": is_claimed,
            "is_claimable": is_claimable,
            "current_progress": user_profile.get('bet_count', 0) if task_id == 'three_bets' else None,
            "target_progress": config.get('condition_bet_count') if task_id == 'three_bets' else None,
            "link": config.get('link') 
        })
    return jsonify(tasks_status_response), 200

@app.route('/api/claim_task_reward', methods=['POST'])
def claim_task_reward_route():
    data = request.json
    user_id = data.get('user_id')
    task_id_to_claim = data.get('task_id')

    if not user_id or not task_id_to_claim:
        return jsonify({"error": "user_id ou task_id manquant"}), 400
    if task_id_to_claim not in TASKS_CONFIG:
        return jsonify({"error": "ID de tâche invalide"}), 400

    task_config = TASKS_CONFIG[task_id_to_claim]
    
    def claim_task_logic(user_p):
        claimed_field = task_config['claimed_field']
        if user_p.get(claimed_field, False):
            raise ValueError("Récompense de tâche déjà réclamée")

        condition_met = True
        if task_id_to_claim == 'three_bets' and user_p.get('bet_count', 0) < task_config['condition_bet_count']:
            condition_met = False
        if task_id_to_claim == 'google' and not user_p.get('email'):
            condition_met = False
        if task_id_to_claim == 'pseudo' and (not user_p.get('pseudo') or user_p.get('pseudo', '').startswith('User_')):
            condition_met = False
        
        if not condition_met:
            raise ValueError("Condition pour réclamer la tâche non remplie")

        user_p['pronocoins_balance'] += task_config['pc_reward']
        user_p['xp'] += task_config['xp_reward']
        user_p[claimed_field] = True 
        user_p, _ = check_and_apply_level_up(user_p)
        return user_p

    try:
        updated_user = update_user_atomic(user_id, claim_task_logic)
        if updated_user:
            logging.info(f"Récompense pour tâche '{task_id_to_claim}' réclamée par {user_id}.")
            return jsonify({
                "message": f"Récompense pour '{TASKS_CONFIG[task_id_to_claim]['name']}' réclamée! (+{task_config['pc_reward']} PC, +{task_config['xp_reward']} XP)",
                "new_balance": updated_user['pronocoins_balance'],
                "new_xp": updated_user['xp'],
                "new_level": updated_user['level'],
                "claimed_task_id": task_id_to_claim,
                "claimed_field_status": updated_user[task_config['claimed_field']]
            }), 200
        else:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 403
    except Exception as e:
        logging.error(f"Erreur interne lors de la réclamation de la tâche {task_id_to_claim} pour {user_id}: {e}")
        return jsonify({"error": "Erreur interne du serveur"}), 500


@app.route('/api/toggle_suivi_prono', methods=['POST'])
def toggle_suivi_prono_route():
    data = request.json
    user_id = data.get('user_id')
    match_id = data.get('match_id')
    if not user_id or not match_id: return jsonify({"error": "user_id ou match_id manquant"}), 400

    suivis = read_csv_as_list_of_dicts(SUIVIS_FILE)
    is_currently_followed = any(s['user_id'] == user_id and s['MatchID'] == match_id for s in suivis)
    
    new_suivis_data = []
    action_message = ""

    if is_currently_followed:
        new_suivis_data = [s for s in suivis if not (s['user_id'] == user_id and s['MatchID'] == match_id)]
        action_message = "Pronostic retiré des suivis."
    else:
        new_suivis_data = list(suivis) 
        new_suivis_data.append({'user_id': user_id, 'MatchID': match_id, 'date_suivi': datetime.now(timezone.utc).isoformat()})
        action_message = "Pronostic ajouté aux suivis."
        
    write_csv_from_list_of_dicts(SUIVIS_FILE, new_suivis_data, SUIVIS_HEADER)
    
    user_suivis_ids = [s['MatchID'] for s in new_suivis_data if s['user_id'] == user_id]
    
    return jsonify({"message": action_message, "pronos_suivis_ids": user_suivis_ids}), 200


@app.route('/api/pronos_suivis', methods=['GET'])
def get_pronos_suivis_route():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({"error": "user_id manquant"}), 400

    suivis = read_csv_as_list_of_dicts(SUIVIS_FILE)
    user_suivis_ids = [s['MatchID'] for s in suivis if s['user_id'] == user_id]
    
    all_pronos = read_csv_as_list_of_dicts(MATCHES_FILE, use_cache=True, cache_var_name="matches_cache", cache_ts_name="matches_cache_timestamp", cache_duration=MATCHES_CACHE_DURATION)
    pronos_suivis_details = [p for p in all_pronos if p['MatchID'] in user_suivis_ids and p.get('Statut','').lower() == 'à venir']
    pronos_suivis_details.sort(key=lambda x: (x.get('Date', 'zzzz'), x.get('Heure', '99:99')))

    return jsonify(pronos_suivis_details), 200

@app.route('/api/paris_en_cours', methods=['GET']) 
def get_paris_en_cours_route():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({"error": "user_id manquant"}), 400
    
    paris = read_csv_as_list_of_dicts(PARIS_FILE)
    paris_en_cours = [p for p in paris if p['user_id'] == user_id and p.get('StatutPari','').lower() == 'en_cours']
    paris_en_cours.sort(key=lambda x: x.get('DatePari', ''), reverse=True) 
    return jsonify(paris_en_cours), 200

@app.route('/api/historique_paris', methods=['GET']) 
def get_historique_paris_route():
    user_id = request.args.get('user_id')
    date_filter = request.args.get('date') 
    if not user_id: return jsonify({"error": "user_id manquant"}), 400

    paris = read_csv_as_list_of_dicts(PARIS_FILE)
    user_all_paris = [p for p in paris if p['user_id'] == user_id] 
    
    if date_filter:
        try:
            datetime.strptime(date_filter, "%Y-%m-%d")
            user_all_paris = [p for p in user_all_paris if p.get('DatePari','').startswith(date_filter)]
        except ValueError:
            return jsonify({"error": "Format de date invalide. Utilisez AAAA-MM-JJ."}), 400

    user_all_paris.sort(key=lambda x: x.get('DatePari', ''), reverse=True)
    return jsonify(user_all_paris), 200

@app.route('/api/bilan', methods=['GET'])
def get_bilan_route():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({"error": "user_id manquant"}), 400

    paris = read_csv_as_list_of_dicts(PARIS_FILE)
    user_paris_termines = [p for p in paris if p['user_id'] == user_id and p.get('StatutPari','').lower() in ['gagne', 'perdu']] 

    total_bets = len(user_paris_termines)
    won_bets = len([p for p in user_paris_termines if p.get('StatutPari','').lower() == 'gagne'])
    lost_bets = total_bets - won_bets
    
    net_gains = 0
    total_staked_on_settled = 0
    for p in user_paris_termines:
        try:
            montant = int(p.get('Montant', 0))
            total_staked_on_settled += montant
            if p.get('StatutPari','').lower() == 'gagne':
                gain_pari_net = int(p.get('Gain', 0)) 
                net_gains += gain_pari_net
            elif p.get('StatutPari','').lower() == 'perdu':
                net_gains -= montant 
        except ValueError:
            logging.warning(f"Donnée de pari invalide pour le bilan de l'utilisateur {user_id}: {p}")

    roi = (net_gains / total_staked_on_settled * 100) if total_staked_on_settled > 0 else 0

    return jsonify({
        "totalBets": total_bets,
        "wonBets": won_bets,
        "lostBets": lost_bets,
        "netGains": round(net_gains, 2),
        "roi": round(roi, 2)
    }), 200

@app.route('/api/bilan_chart_data', methods=['GET'])
def get_bilan_chart_data_route():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({"error": "user_id manquant"}), 400

    paris = read_csv_as_list_of_dicts(PARIS_FILE)
    user_paris_regles = [p for p in paris if p['user_id'] == user_id and p.get('StatutPari','').lower() in ['gagne', 'perdu']]
    
    user_paris_regles.sort(key=lambda x: x.get('DatePari', ''))

    daily_stats = defaultdict(lambda: {"gagnes": 0, "perdus": 0, "pnl_jour": 0, "paris_regles": 0})
    
    for p in user_paris_regles:
        try:
            date_pari_str = p.get('DatePari', '').split('T')[0] 
            if not date_pari_str: continue

            montant = int(p.get('Montant', 0))
            daily_stats[date_pari_str]["paris_regles"] += 1

            if p.get('StatutPari','').lower() == 'gagne':
                daily_stats[date_pari_str]["gagnes"] += 1
                gain_net_pari = int(p.get('Gain', 0)) 
                daily_stats[date_pari_str]["pnl_jour"] += gain_net_pari
            elif p.get('StatutPari','').lower() == 'perdu':
                daily_stats[date_pari_str]["perdus"] += 1
                daily_stats[date_pari_str]["pnl_jour"] -= montant
        except ValueError:
            logging.warning(f"Donnée de pari invalide pour le graphique bilan de {user_id}: {p}")
            continue

    sorted_dates = sorted(daily_stats.keys())
    
    labels = []
    data_gagnes = []
    data_perdus = []
    data_paris_regles = []
    data_pnl_cumule = []
    pnl_cumulatif_actuel = 0

    for dt_str in sorted_dates:
        labels.append(datetime.strptime(dt_str, "%Y-%m-%d").strftime("%d/%m")) 
        stats_jour = daily_stats[dt_str]
        data_gagnes.append(stats_jour["gagnes"])
        data_perdus.append(stats_jour["perdus"])
        data_paris_regles.append(stats_jour["paris_regles"])
        pnl_cumulatif_actuel += stats_jour["pnl_jour"]
        data_pnl_cumule.append(pnl_cumulatif_actuel)

    return jsonify({
        "labels": labels,
        "gagnes": data_gagnes,
        "perdus": data_perdus,
        "paris_regles": data_paris_regles, 
        "pnl_cumule": data_pnl_cumule
    }), 200


@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard_route():
    users = read_csv_as_list_of_dicts(USERS_FILE)
    leaderboard_data = []
    for u in users:
        try:
            leaderboard_data.append({
                'user_id': u['user_id'],
                'pseudo': u.get('pseudo', 'N/A'),
                'level': int(u.get('level', 1)),
                'xp': int(u.get('xp', 0)),
                'pronocoins_balance': int(u.get('pronocoins_balance', 0)),
                'join_date': u.get('join_date', '') 
            })
        except ValueError:
            logging.warning(f"Donnée utilisateur invalide pour le classement: {u}")
    
    leaderboard_data.sort(key=lambda x: (x['pronocoins_balance'], x['level'], x['xp']), reverse=True)
    
    return jsonify(leaderboard_data[:20]) 


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
