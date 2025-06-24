from flask import Flask, render_template_string, request, redirect, url_for
import random
import threading
import webbrowser
import os
import json
import time

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Variables globales ---
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

PLAYERS_FILE = os.path.join(DATA_DIR, 'players.json')
ENCOUNTERS_DIR = os.path.join(DATA_DIR, 'encounters')
os.makedirs(ENCOUNTERS_DIR, exist_ok=True)

initiative_data = []
current_turn_index = 0

# --- Fonctions Logiques ---

def sort_participants():
    """Trie les participants par initiative, puis par nom."""
    global initiative_data
    initiative_data.sort(key=lambda p: (p.get('initiative_roll', 0), p.get('name', '')), reverse=True)

def get_participant_status(p):
    """Calcule l'état et le malus du participant en fonction de ses blessures."""
    p = p.copy()
    status = {'text': '', 'class': '', 'malus': 0}
    
    # Si Extra, vulnérable et sortie rapide
    if p.get('type', 'Extra') == 'Extra':
        if p.get('wounds', 0) >= 1:
            status['text'] = 'Hors Combat'
            status['class'] = 'status-dead'
    # Si Joker, plus résistant
    else:
        wounds = p.get('wounds', 0)
        if wounds > 0:
            # Malus par blessure
            status['malus'] = wounds
            status['class'] = 'status-wounded'
            status['text'] = f"-{wounds}"
            
            # Incapacité à 3 blessures, Mort à 5
            if wounds >= 5:
                status['text'] = 'Mort'
                status['class'] = 'status-dead'
            elif wounds >= 4:
                status['text'] = 'Incapacité'
                status['class'] = 'status-incapacitated'
                
    p['status'] = status
    return p

def update_participant_statuses():
    """Met à jour le statut de tous les participants."""
    global initiative_data
    for i, p in enumerate(initiative_data):
        initiative_data[i] = get_participant_status(p)

# --- Fonctions de sauvegarde/chargement ---

def save_players():
    """Sauvegarde les joueurs actuels dans un fichier JSON."""
    players = [p for p in initiative_data if p.get('role') == 'player']
    with open(PLAYERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

def load_players():
    """Charge les joueurs depuis le fichier JSON."""
    global initiative_data
    if os.path.exists(PLAYERS_FILE):
        with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
            players = json.load(f)
            # Ne garder que les joueurs dans l'initiative_data actuelle
            initiative_data = [p for p in initiative_data if p.get('role') != 'player']
            # Ajouter les joueurs chargés
            initiative_data.extend(players)
            sort_participants()
            return True
    return False

def save_encounter(name):
    """Sauvegarde un combat (monstres et alliés) dans un fichier JSON."""
    encounter = {
        'name': name,
        'monsters': [p for p in initiative_data if p.get('role') == 'monster'],
        'allies': [p for p in initiative_data if p.get('role') == 'ally'],
        'date_created': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    filename = os.path.join(ENCOUNTERS_DIR, f"{name.replace(' ', '_')}.json")
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(encounter, f, ensure_ascii=False, indent=2)
    return filename

def load_encounter(filename):
    """Charge un combat depuis un fichier JSON et l'ajoute à l'initiative actuelle."""
    global initiative_data
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            encounter = json.load(f)
            # Ajouter les monstres et alliés à l'initiative_data actuelle
            initiative_data.extend(encounter.get('monsters', []))
            initiative_data.extend(encounter.get('allies', []))
            # Réinitialiser les initiatives pour les entités ajoutées
            for p in initiative_data:
                status = get_participant_status(p)['status']['class']
                if status not in ['status-dead', 'status-out']:
                    # Les joueurs ne relancent pas, leur MJ saisit la valeur
                    if p.get('role') != 'player':
                        p['initiative_roll'] = random.randint(1, 20)
                        p['is_critical'] = False
            sort_participants()
            return True
    return False

def list_encounters():
    """Liste tous les combats enregistrés."""
    encounters = []
    for filename in os.listdir(ENCOUNTERS_DIR):
        if filename.endswith('.json'):
            file_path = os.path.join(ENCOUNTERS_DIR, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                encounter = json.load(f)
                encounters.append({
                    'name': encounter.get('name', 'Sans nom'),
                    'filename': filename,
                    'date_created': encounter.get('date_created', ''),
                    'monster_count': len(encounter.get('monsters', [])),
                    'ally_count': len(encounter.get('allies', []))
                })
    return encounters

# --- Templates HTML ---

home_template = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Initiative Tracker</title>
    <meta http-equiv="refresh" content="{{ refresh_rate }}" >
    <style>
        body { background-color: #111; color: #eee; font-family: Arial, sans-serif; margin: 0; padding: 0; }
        .container { padding: 20px; max-width: 500px; margin: 0 auto; background-color: #2d2d2d; padding: 20px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.5); }
        h1, h2 { color: #d6a248; text-align: center; border-bottom: 2px solid #d6a248; padding-bottom: 10px; }
        a { color: #7da2d6; }
        .info { text-align: center; margin-bottom: 20px; font-size: 0.9em; color: #aaa; }
        .participant {
            display: flex; flex-wrap: wrap; align-items: center; padding: 12px; margin-bottom: 8px; border-radius: 5px; 
            border-left: 5px solid transparent; transition: all 0.3s ease;
        }
        .participant.player { border-left-color: #4a90e2; background-color: #3a3a3a; }
        .participant.ally { border-left-color: #2ecc71; background-color: #3a3a3a; }
        .participant.monster { border-left-color: #e24a4a; background-color: #3a3a3a; }
        .participant.active { background-color: #4a4a4a; box-shadow: 0 0 10px #d6a248; }
        .participant.status-out { background-color: #444; color: #888; text-decoration: line-through; }
        .participant.status-incapacitated { background-color: #5a2d2d; }
        .participant.status-dead { background-color: #1a1a1a; color: #666; border-left-color: #000; text-decoration: line-through; }
        .rank { font-weight: bold; font-size: 1.2em; min-width: 30px; }
        .rank::after { content: '.'; }
        .name { font-weight: bold; font-size: 1.1em; flex-grow: 1; }
        .joker-tag { color: #d6a248; font-weight: bold; margin-left: 8px; }
        .initiative-roll { font-style: italic; color: #ccc; margin-left: 10px; }
        .crit-bonus { background-color: #d6a248; color: #1e1e1e; padding: 3px 8px; border-radius: 10px; font-size: 0.8em; font-weight: bold; margin-left: 10px; }
        .status-display { margin-left: 10px; padding: 3px 8px; border-radius: 10px; font-size: 0.9em; }
        .status-wounded { background-color: #b8860b; color: #fff; }
        .status-incapacitated { background-color: #8b0000; color: #fff; }
        .status-dead { background-color: #000; color: #888; border: 1px solid #555; }
        .btn { background-color: #4a90e2; color: white; padding: 8px 15px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 1em; transition: background-color 0.3s; }
        .btn:hover { background-color: #357abd; }
        .btn-danger { background-color: #e24a4a; }
        .btn-danger:hover { background-color: #c0392b; }
        .btn-success { background-color: #2ecc71; }
        .btn-success:hover { background-color: #27ae60; }
        .actions { display: flex; align-items: center; gap: 5px; margin-left: auto; }
        .wound-controls { display: flex; align-items: center; gap: 5px; margin-left: 15px; }
        .wound-controls .btn { padding: 2px 8px; font-size: 1em; }
        .initiative-input { width: 60px; padding: 5px; border-radius: 4px; border: 1px solid #555; background-color: #2c2c2c; color: #e0e0e0; text-align: center; }
        .form-container { background-color: #3a3a3a; padding: 20px; border-radius: 8px; margin-top: 20px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; color: #ccc; }
        .form-group input[type="text"] { width: calc(100% - 22px); padding: 10px; border-radius: 4px; border: 1px solid #555; background-color: #2c2c2c; color: #e0e0e0; }
        .form-group select { width: 100%; padding: 10px; border-radius: 4px; border: 1px solid #555; background-color: #2c2c2c; color: #e0e0e0; }
        .main-controls { text-align: center; margin-top: 20px; display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 15px; }
        .main-controls .btn { padding: 12px 25px; font-size: 1.1em; }
        .encounters-list { max-height: 300px; overflow-y: auto; margin-top: 15px; }
        .encounter-item { background-color: #2c2c2c; padding: 10px; margin-bottom: 10px; border-radius: 5px; display: flex; justify-content: space-between; align-items: center; }
        .encounter-meta { color: #aaa; font-size: 0.9em; margin: 0 15px; }
        .initiative-display { display: inline-block; width: 60px; padding: 5px; border-radius: 4px; border: 1px solid #555; background-color: #2c2c2c; color: #e0e0e0; text-align: center; cursor: pointer; user-select: none; }
        .initiative-display:hover { background-color: #454545; }
        .keypad-modal { position: fixed; z-index: 1000; background-color: #3a3a3a; border: 1px solid #d6a248; border-radius: 8px; box-shadow: 0 5px 15px rgba(0,0,0,0.5); padding: 10px; }
        .keypad { display: grid; grid-template-columns: repeat(5, 1fr); gap: 5px; }
        .keypad-btn { background-color: #4a90e2; color: white; border: none; border-radius: 4px; padding: 10px; font-size: 1.2em; cursor: pointer; transition: background-color 0.3s; }
        .keypad-btn:hover { background-color: #357abd; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Gestionnaire d'Initiative JDR</h1>
        <div class="info"><a href="/view" target="_blank">Ouvrir la vue OBS</a></div>
        
        <div class="initiative-list">
            <h2>Ordre d'Initiative</h2>
            <form action="{{ url_for('update_initiatives') }}" method="post">
                {% for p in participants %}
                <div class="participant {{ p.role }} {{ 'active' if loop.index0 == current_turn_index }} {{ p.status.class }}">
                    <span class="rank">{{ loop.index }}</span>
                    <span class="name">{{ p.name }}{% if p.type == 'Joker' %}<span class="joker-tag">🏴</span>{% endif %}</span>
                    
                    {% if p.is_player %}
                        <div class="initiative-input-container">
                            <span class="initiative-display" data-player-index="{{ loop.index0 }}">{{ p.initiative_roll }}</span>
                            <input type="hidden" name="p_{{ loop.index0 }}" id="p_{{ loop.index0 }}_input" value="{{ p.initiative_roll }}">
                        </div>
                    {% else %}
                        <span class="initiative-roll">({{ p.initiative_roll }})</span>
                    {% endif %}

                    {% if p.is_critical %}
                    <span class="crit-bonus">CRITIQUE! (+2)</span>
                    {% endif %}

                    {% if p.status.text %}
                    <span class="status-display {{ p.status.class }}">{{ p.status.text }}</span>
                    {% endif %}

                    <div class="wound-controls">
                        <span>Blessures: {{ p.wounds }}</span>
                        <button type="submit" class="btn" formaction="{{ url_for('add_wound', index=loop.index0) }}">+</button>
                        <button type="submit" class="btn" formaction="{{ url_for('remove_wound', index=loop.index0) }}">-</button>
                    </div>

                    <div class="actions">
                        <button type="submit" class="btn btn-danger" formaction="{{ url_for('remove_participant', index=loop.index0) }}">X</button>
                    </div>
                </div>
                {% endfor %}
                <div style="text-align: center; margin-top: 20px;">
                    <button type="submit" class="btn">Mettre à jour les initiatives</button>
                </div>
            </form>
            {% if not participants %}
            <p style="text-align:center;">Aucun participant pour le moment.</p>
            {% endif %}
        </div>

        <div class="form-container">
            <h2>Ajouter un Participant</h2>
            <form action="{{ url_for('add') }}" method="post">
                <div class="form-group">
                    <label for="name">Nom</label>
                    <input type="text" id="name" name="name" required>
                </div>
                <div class="form-group">
                    <label for="is_player">Catégorie</label>
                    <select id="is_player" name="is_player">
                        <option value="player">Joueur (Joker)</option>
                        <option value="ally">Allié</option>
                        <option value="monster">Monstre</option>
                    </select>
                </div>
                <div class="form-group" id="type-form-group">
                    <label for="type">Type (pour alliés et monstres)</label>
                    <select id="type" name="type">
                        <option value="Extra">Extra (Sbire)</option>
                        <option value="Joker">Joker (Important)</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-success">Ajouter</button>
            </form>
            
            <h2>Gérer les Combats</h2>
            <form action="{{ url_for('save_encounter_route') }}" method="post" class="form-container">
                <div class="form-group">
                    <label for="encounter_name">Nom du Combat</label>
                    <input type="text" id="encounter_name" name="encounter_name" required>
                </div>
                <button type="submit" class="btn btn-success">Sauvegarder Combat</button>
            </form>
            
            <h3>Combats Disponibles</h3>
            <div class="encounters-list">
                {% for encounter in encounters %}
                <div class="encounter-item">
                    <strong>{{ encounter.name }}</strong>
                    <span class="encounter-meta">
                        ({{ encounter.monster_count }} monstres, {{ encounter.ally_count }} alliés)
                        <br>Créé le: {{ encounter.date_created }}
                    </span>
                    <form action="{{ url_for('load_encounter_route', filename=encounter.filename) }}" method="post">
                        <button type="submit" class="btn">Charger</button>
                    </form>
                </div>
                {% else %}
                <div class="info">Aucun combat enregistré.</div>
                {% endfor %}
            </div>
        </div>
        <div class="main-controls">
            <form action="/next" method="post">
                <button type="submit" class="btn btn-success">Tour Suivant</button>
            </form>
            <form action="/new_round" method="post">
                <button type="submit" class="btn">Nouvelle Manche</button>
            </form>
            <form action="/reset_combat" method="post">
                <button type="submit" class="btn">Réinitialiser Combat</button>
            </form>
            <form action="{{ url_for('reset') }}" method="post" onsubmit="return confirm('Êtes-vous sûr de vouloir tout réinitialiser?')">
                <button class="btn btn-danger">Réinitialiser Tout</button>
            </form>

            <form action="{{ url_for('save_players_route') }}" method="post">
                <button class="btn">Sauvegarder Joueurs</button>
            </form>
            
            <form action="{{ url_for('load_players_route') }}" method="post">
                <button class="btn">Charger Joueurs</button>
            </form>
        </div>
    </div>

    <div id="initiative-keypad-modal" class="keypad-modal" style="display:none;">
        <div class="keypad">
            {% for i in range(1, 21) %}
            <button type="button" class="keypad-btn" data-value="{{ i }}">{{ i }}</button>
            {% endfor %}
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const categorySelect = document.getElementById('is_player');
            const typeFormGroup = document.getElementById('type-form-group');
            const typeSelect = document.getElementById('type');

            function toggleTypeField() {
                if (categorySelect.value === 'player') {
                    typeFormGroup.style.display = 'none';
                    typeSelect.disabled = true;
                } else {
                    typeFormGroup.style.display = 'block';
                    typeSelect.disabled = false;
                }
            }

            // Vérification initiale au chargement de la page
            toggleTypeField();

            // Ajout de l'écouteur d'événement pour les changements
            categorySelect.addEventListener('change', toggleTypeField);

            const modal = document.getElementById('initiative-keypad-modal');
            let currentTargetDisplay = null;
            let currentTargetInput = null;

            document.querySelectorAll('.initiative-display').forEach(display => {
                display.addEventListener('click', function(event) {
                    event.stopPropagation();
                    const playerIndex = this.dataset.playerIndex;
                    currentTargetDisplay = this;
                    currentTargetInput = document.getElementById(`p_${playerIndex}_input`);
                    const rect = this.getBoundingClientRect();
                    modal.style.top = `${rect.bottom + window.scrollY + 5}px`;
                    modal.style.left = `${rect.left + window.scrollX}px`;
                    modal.style.display = 'block';
                });
            });

            document.querySelectorAll('.keypad-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const value = this.dataset.value;
                    if (currentTargetDisplay && currentTargetInput) {
                        currentTargetDisplay.textContent = value;
                        currentTargetInput.value = value;
                    }
                    modal.style.display = 'none';
                });
            });

            window.addEventListener('click', function(event) {
                if (modal.style.display === 'block' && !modal.contains(event.target)) {
                    const isDisplayClick = event.target.classList.contains('initiative-display');
                    if (!isDisplayClick) {
                        modal.style.display = 'none';
                    }
                }
            });
        });
    </script>
</body>
</html>
"""

view_template = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Vue Initiative</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body { font-family: sans-serif; background-color: #1e1e1e; color: #e0e0e0; margin: 0; padding: 10px; }
        .container { max-width: 500px; margin: 0 auto; }
        .participant { display: flex; align-items: center; padding: 10px; margin-bottom: 5px; border-radius: 5px; border-left: 5px solid transparent; }
        .participant.player { border-left-color: #4a90e2; background-color: #3a3a3a; }
        .participant.ally { border-left-color: #2ecc71; background-color: #3a3a3a; }
        .participant.monster { border-left-color: #e24a4a; background-color: #3a3a3a; }
        .participant.active { background-color: #4a4a4a; box-shadow: 0 0 8px #d6a248; }
        .participant.status-out { background-color: #444; color: #888; text-decoration: line-through; }
        .participant.status-incapacitated { background-color: #5a2d2d; }
        .participant.status-dead { background-color: #1a1a1a; color: #666; border-left-color: #000; text-decoration: line-through; }
        .rank { font-weight: bold; font-size: 1.1em; min-width: 25px; }
        .rank::after { content: '.'; }
        .name { font-weight: bold; font-size: 1em; flex-grow: 1; }
        .joker-tag { color: #d6a248; font-weight: bold; margin-left: 6px; font-size: 0.9em; }
        .initiative-roll { font-style: italic; color: #ccc; margin-left: 8px; }
        .crit-bonus { background-color: #d6a248; color: #1e1e1e; padding: 2px 6px; border-radius: 8px; font-size: 0.7em; font-weight: bold; margin-left: 8px; }
        .status-display { margin-left: 10px; padding: 2px 6px; border-radius: 8px; font-size: 0.8em; }
        .status-wounded { background-color: #b8860b; color: #fff; }
        .status-incapacitated { background-color: #8b0000; color: #fff; }
        .status-dead { background-color: #000; color: #888; border: 1px solid #555; }
    </style>
</head>
<body>
    <div class="container">
    {% for p in participants %}
    <div class="participant {{ p.role }} {{ 'active' if loop.index0 == current_turn_index }} {{ p.status.class }}">
        <span class="rank">{{ loop.index }}</span>
        <span class="name">{{ p.name }}</span>
        <span class="initiative-roll">({{ p.initiative_roll }})</span>
        {% if p.is_critical %}
        <span class="crit-bonus">CRITIQUE! (+2)</span>
        {% endif %}
        {% if p.status.text %}
        <span class="status-display {{ p.status.class }}">{{ p.status.text }}</span>
        {% endif %}
    </div>
    {% endfor %}
    </div>
</body>
</html>
"""

# --- Routes Flask ---

@app.route('/')
def index():
    update_participant_statuses()
    encounters = list_encounters()
    return render_template_string(home_template, participants=initiative_data, current_turn_index=current_turn_index, encounters=encounters)

@app.route('/view')
def view():
    processed_participants = [get_participant_status(p.copy()) for p in initiative_data]
    return render_template_string(view_template, participants=processed_participants, current_turn_index=current_turn_index)

@app.route('/add', methods=['POST'])
def add():
    name = request.form.get('name')
    role = request.form.get('is_player')  # Renommé pour plus de clarté
    
    # Déterminer le type de participant
    if role == 'player':
        # Les joueurs sont toujours des Jokers
        is_player = True
        p_type = 'Joker'
        participant_role = 'player'
    elif role == 'ally':
        # Nouvelle catégorie : Allié
        is_player = False
        p_type = request.form.get('type', 'Extra')  # Peut être Joker ou Extra
        participant_role = 'ally'
    else:  # 'monster'
        is_player = False
        p_type = request.form.get('type', 'Extra')
        participant_role = 'monster'
        
    if name:
        initiative_data.append({
            'name': name,
            'is_player': is_player,
            'role': participant_role,  # Utiliser la variable claire
            'type': p_type,
            'wounds': 0,
            'initiative_roll': 0,
            'is_critical': False
        })
        sort_participants()
    return redirect(url_for('index'))

@app.route('/remove/<int:index>', methods=['POST'])
def remove_participant(index):
    global current_turn_index
    if 0 <= index < len(initiative_data):
        # Ajuster l'index AVANT de supprimer
        if index < current_turn_index:
            current_turn_index -= 1
        
        del initiative_data[index]

        # Après suppression, s'assurer que l'index n'est pas hors limites.
        if initiative_data and current_turn_index >= len(initiative_data):
            current_turn_index = 0
        elif not initiative_data:
            current_turn_index = 0
            
    return redirect(url_for('index'))

@app.route('/add_wound/<int:index>', methods=['POST'])
def add_wound(index):
    if 0 <= index < len(initiative_data):
        initiative_data[index]['wounds'] = initiative_data[index].get('wounds', 0) + 1
    return redirect(url_for('index'))

@app.route('/remove_wound/<int:index>', methods=['POST'])
def remove_wound(index):
    if 0 <= index < len(initiative_data):
        initiative_data[index]['wounds'] = max(0, initiative_data[index].get('wounds', 0) - 1)
    return redirect(url_for('index'))

@app.route('/next', methods=['POST'])
def next_turn():
    global current_turn_index
    if not initiative_data:
        return redirect(url_for('index'))

    # Chercher le prochain participant valide en partant de l'actuel
    for i in range(len(initiative_data)):
        next_index = (current_turn_index + 1 + i) % len(initiative_data)
        p = get_participant_status(initiative_data[next_index].copy())
        if p['status']['class'] != 'status-out':
            current_turn_index = next_index
            return redirect(url_for('index'))
    
    # Si aucun participant valide n'est trouvé, ne pas changer le tour
    return redirect(url_for('index'))

@app.route('/reset_combat', methods=['POST'])
def reset_combat():
    """Réinitialise le combat en conservant les joueurs, mais en supprimant les monstres et alliés."""
    global initiative_data, current_turn_index
    # Ne garder que les joueurs
    initiative_data = [p for p in initiative_data if p.get('role') == 'player']
    current_turn_index = 0
    return redirect(url_for('index'))

@app.route('/reset', methods=['POST'])
def reset():
    global initiative_data, current_turn_index
    initiative_data = []
    current_turn_index = 0
    return redirect(url_for('index'))

@app.route('/new_round', methods=['POST'])
def new_round():
    global current_turn_index
    current_turn_index = 0
    for p in initiative_data:
        # Vérifie le statut avant de faire quoi que ce soit
        status_info = get_participant_status(p)
        
        # On ne touche pas aux morts ou hors-combat
        if status_info['status']['class'] in ['status-dead', 'status-out']:
            continue

        if not p.get('is_player', False): # Lancer auto pour les monstres et alliés
            roll = random.randint(1, 20)
            p['initiative_roll'] = roll
            p['is_critical'] = (roll == 20)
        else: # Réinitialiser pour les joueurs
            p['initiative_roll'] = 0
            p['is_critical'] = False
            
    sort_participants()
    
    # Assurer que le premier tour est sur un participant valide
    current_turn_index = -1 # Réinitialiser au cas où personne n'est valide
    if initiative_data:
        for i, p_data in enumerate(initiative_data):
            p_status = get_participant_status(p_data.copy())
            if p_status['status']['class'] not in ['status-dead', 'status-out']:
                current_turn_index = i
                break
    
    return redirect(url_for('index'))

@app.route('/update_initiatives', methods=['POST'])
def update_initiatives():
    for i, p in enumerate(initiative_data):
        if p['is_player']:
            try:
                roll = int(request.form.get(f'p_{i}'))
                if 1 <= roll <= 20:
                    p['initiative_roll'] = roll
                    p['is_critical'] = (roll == 20)
            except (ValueError, TypeError):
                pass # Garder l'ancienne valeur si l'entrée est invalide
    sort_participants()
    return redirect(url_for('index'))

# --- Démarrage de l'application ---

def open_browser():
    """Ouvre le navigateur web sur la page d'accueil."""
    print("-----------------------------------------------------")
    print("Interface de GESTION ouverte dans votre navigateur.")
    print(f"Pour la vue OBS, utilisez: http://127.0.0.1:5000/view")
    print("-----------------------------------------------------")
    webbrowser.open_new("http://127.0.0.1:5000/")

# --- Routes pour la sauvegarde et le chargement ---

@app.route('/save_players', methods=['POST'])
def save_players_route():
    """Sauvegarde les joueurs actuels."""
    save_players()
    return redirect(url_for('index'))

@app.route('/load_players', methods=['POST'])
def load_players_route():
    """Charge les joueurs sauvegardés."""
    load_players()
    return redirect(url_for('index'))

@app.route('/save_encounter', methods=['POST'])
def save_encounter_route():
    """Sauvegarde un combat."""
    name = request.form.get('encounter_name')
    if name:
        save_encounter(name)
    return redirect(url_for('index'))

@app.route('/load_encounter/<filename>', methods=['POST'])
def load_encounter_route(filename):
    """Charge un combat."""
    file_path = os.path.join(ENCOUNTERS_DIR, filename)
    load_encounter(file_path)
    return redirect(url_for('index'))

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1, open_browser).start()
    app.run(debug=True, use_reloader=True)