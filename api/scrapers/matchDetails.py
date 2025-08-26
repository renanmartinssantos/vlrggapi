
import requests
from bs4 import BeautifulSoup
import logging
from utils.utils import headers
from api.scrapers.matrix_extractor import extract_player_matrix, get_performance_data
import re

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper_debug.log", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('matchDetails')

def extract_map_stats(map_div):
    """Extrair estatísticas detalhadas de um mapa específico."""
    stats = []
    if not map_div:
        return stats
    
    for table in map_div.select('table.wf-table-inset.mod-overview'):
        for row in table.select('tbody tr'):
            player = {}
            player_name_div = row.select_one('.mod-player .text-of')
            player['player'] = player_name_div.get_text(strip=True) if player_name_div else None
            team_div = row.select_one('.mod-player .ge-text-light')
            player['team'] = team_div.get_text(strip=True) if team_div else None
            agents = []
            for agent_span in row.select('.mod-agents img'):
                agent_name = agent_span.get('alt')
                agent_img = 'https://www.vlr.gg' + agent_span.get('src') if agent_span.get('src', '').startswith('/') else agent_span.get('src')
                agents.append({'name': agent_name, 'img': agent_img})
            player['agents'] = agents
            
            def get_stat(td, side):
                span = td.select_one(f'.side.mod-side.mod-{side}')
                if not span:
                    span = td.select_one(f'.side.mod-{side}')
                return span.get_text(strip=True) if span else None
                
            stat_cols = row.select('td.mod-stat, td.mod-stat.mod-vlr-kills, td.mod-stat.mod-vlr-deaths, td.mod-stat.mod-vlr-assists, td.mod-stat.mod-kd-diff, td.mod-stat.mod-fb, td.mod-stat.mod-fd, td.mod-stat.mod-fk-diff')
            stat_map = [
                ('rating', 0), ('acs', 1), ('kills', 2), ('deaths', 3), ('assists', 4), ('kd_diff', 5),
                ('kast', 6), ('adr', 7), ('hs_pct', 8), ('fk', 9), ('fd', 10), ('fk_diff', 11)
            ]
            for stat, idx in stat_map:
                if idx < len(stat_cols):
                    player[stat] = {
                        'both': get_stat(stat_cols[idx], 'both'),
                        'attack': get_stat(stat_cols[idx], 't'),
                        'defend': get_stat(stat_cols[idx], 'ct')
                    }
                else:
                    player[stat] = {'both': None, 'attack': None, 'defend': None}
            stats.append(player)
    return stats

def extract_all_map_stats(soup):
    """Extrair estatísticas gerais (todos os mapas)."""
    stats = []
    stats_game = soup.select_one('.vm-stats-game[data-game-id="all"]')
    if not stats_game:
        return stats
    
    return extract_map_stats(stats_game)

def get_match_details(match_url):
    # Function to extract match details from the given URL
    if match_url.isdigit():
        url = f"https://www.vlr.gg/{match_url}"
    elif not match_url.startswith("https://"):
        url = f"https://www.vlr.gg{match_url}"
    else:
        url = match_url
        
    logger.info(f"Making request to: {url}")
    resp = requests.get(url, headers=headers)
    logger.info(f"Response status code: {resp.status_code}")
    if resp.status_code != 200:
        error = {
            "data": {
                "status": resp.status_code,
                "error": f"Failed to fetch match details. Status code: {resp.status_code}"
            }
        }
        return error
    soup = BeautifulSoup(resp.text, 'html.parser')
    status = resp.status_code
    match_status = "Unknown"
    if soup.select_one(".match-header-vs-note.match-header-vs-note-upcoming"):
        match_status = "Upcoming"
    elif soup.select_one(".match-header-vs-note.match-header-vs-note-live"):
        match_status = "Live"
    else:
        match_status = "Completed"
    tournament_name = None
    tournament_element = soup.select_one(".match-header-event div[style='font-weight: 700;']")
    if tournament_element:
        tournament_name = tournament_element.get_text(strip=True)
    tournament_stage = None
    stage_element = soup.select_one(".match-header-event-series")
    if stage_element:
        tournament_stage = stage_element.get_text(strip=True)
    logger.info(f"Tournament Name: {tournament_name}")
    logger.info(f"Tournament Stage: {tournament_stage}")
    match_date = None
    match_time = None
    date_div = soup.select_one(".match-header-date .moment-tz-convert[data-moment-format='dddd, MMMM Do']")
    if date_div:
        match_date = date_div.get("data-utc-ts")
    time_div = soup.select_one(".match-header-date .moment-tz-convert[data-moment-format='h:mm A z']")
    if time_div:
        match_time = time_div.get("data-utc-ts")
    patch = None
    patch_div = soup.select_one(".match-header-date [style*='font-style: italic']")
    if patch_div:
        patch = patch_div.get_text(strip=True)
    logger.info(f"Match Date: {match_date}")
    logger.info(f"Patch: {patch}")
    match_notes = None
    notes_div = soup.select_one(".match-header-note")
    if notes_div:
        match_notes = notes_div.get_text(strip=True)
    logger.info(f"Match Notes: {match_notes}")
    stats = extract_all_map_stats(soup)
    match_maps = extract_match_maps(soup, url)
    
    # Add debug info
    debug_info = {
        "url": url,
        "match_maps_count": len(match_maps),
        "players_count": len(stats),
        "status_code": resp.status_code,
        "has_matrix": any(map_data.get('performance', {}).get('player_matrix', {}).get('column_players') for map_data in match_maps),
        "map_ids": [m.get('game_id') for m in match_maps],
        "matrix_sizes": [
            {
                "game_id": m.get('game_id'),
                "columns": len(m.get('performance', {}).get('player_matrix', {}).get('column_players', [])),
                "rows": len(m.get('performance', {}).get('player_matrix', {}).get('row_players', []))
            } 
            for m in match_maps
        ]
    }
    
    result = {
        "status": status,
        "match_id": re.sub(r'[^0-9]', '', url.split("/")[3]),
        "match_status": match_status,
        "tournament": {
            "name": tournament_name,
            "stage": tournament_stage
        },
        "match_date": match_date,
        "patch": patch,
        "notes": match_notes,
        "stats": stats,
        "match_maps": match_maps,
        "debug_info": debug_info
    }
    segments = {"status": status, "match_details": result}
    data = {"data": segments}
    return data

def extract_match_maps(soup, match_url):
    match_maps = []
    
    # Extrair informações dos mapas a partir das abas na página principal
    # Tentando vários seletores para garantir que encontramos os mapas
    map_tabs = soup.select('.vm-stats-gamesnav-item:not([data-game-id="all"])')
    
    # Se não encontrou, tente outros seletores na página principal
    if not map_tabs:
        map_tabs = soup.select('.vm-stats-game:not([data-game-id="all"])')
    
    # Se ainda não encontrou, tente um seletor mais genérico
    if not map_tabs:
        map_tabs = soup.select('.vm-stats-container .vm-stats-game')
        # Filtra apenas os que têm game_id definido e não é "all"
        map_tabs = [tab for tab in map_tabs if tab.get('data-game-id') and tab.get('data-game-id') != 'all']
    
    # Se não encontrou na página principal, tenta extrair da aba de performance
    if not map_tabs:
        logger.info("Não encontrou abas de mapas na página principal, buscando na aba de performance")
        performance_soup = get_performance_data(match_url)
        if performance_soup:
            # Tenta vários seletores na aba de performance também
            map_tabs = performance_soup.select('.vm-stats-gamesnav-item:not([data-game-id="all"])')
            if not map_tabs:
                map_tabs = performance_soup.select('.vm-stats-game:not([data-game-id="all"])')
            if not map_tabs:
                map_tabs = performance_soup.select('.vm-stats-container .vm-stats-game')
                map_tabs = [tab for tab in map_tabs if tab.get('data-game-id') and tab.get('data-game-id') != 'all']
            
            logger.info(f"Encontradas {len(map_tabs)} abas de mapas na aba de performance")
    
    # Se mesmo assim não encontrou, vamos tentar um fallback para mapas únicos
    # Muitas vezes, partidas com um único mapa não têm as abas
    if not map_tabs:
        logger.info("Nenhum mapa encontrado. Tentando fallback para mapa único")
        
        # Criar um mapa "virtual" baseado nos dados disponíveis
        map_name = "Unknown"
        
        # Procurar o nome do mapa em algum lugar da página
        map_name_elem = soup.select_one('.map-text')
        if map_name_elem:
            map_name = map_name_elem.get_text(strip=True)
        
        # Criar um mapa dummy para garantir pelo menos uma entrada
        map_data = {
            'map_name': map_name,
            'score': team_scores,
            'teams': teams,
            'game_id': "all",
            'player_stats': [],
            'performance': {
                'player_matrix': {},
            },
            'rounds': []
        }
        
        # Tentar obter dados de performance usando matrix_extractor
        try:
            matrix_data = get_performance_data(match_url, "all")
            if matrix_data:
                map_data['performance'] = matrix_data
                logger.info(f"Matriz de jogador vs jogador extraída para o mapa {map_name}")
                
                # Se temos dados de matrix, usar nomes reais dos jogadores
                player_stats = []
                team1_players = []
                team2_players = []
                
                # Extrair jogadores da linha (time 1)
                for player in matrix_data.get('player_matrix', {}).get('row_players', []):
                    if isinstance(player, dict) and 'name' in player:
                        team1_players.append(player.get('name'))
                    elif isinstance(player, str):
                        team1_players.append(player)
                
                # Extrair jogadores da coluna (time 2)
                for player in matrix_data.get('player_matrix', {}).get('column_players', []):
                    if isinstance(player, dict) and 'name' in player:
                        team2_players.append(player.get('name'))
                    elif isinstance(player, str):
                        team2_players.append(player)
                
                # Criar entradas de jogadores para o time 1
                for player_name in team1_players:
                    player_stats.append({
                        'player_name': player_name,
                        'team': teams[0] if len(teams) > 0 else "Team A",
                        'agent': None,
                        'stats': {
                            'rating': {'both': None, 'attack': None, 'defend': None},
                            'acs': {'both': None, 'attack': None, 'defend': None},
                            'kills': {'both': None, 'attack': None, 'defend': None},
                            'deaths': {'both': None, 'attack': None, 'defend': None},
                            'assists': {'both': None, 'attack': None, 'defend': None}
                        }
                    })
                
                # Criar entradas de jogadores para o time 2
                for player_name in team2_players:
                    player_stats.append({
                        'player_name': player_name,
                        'team': teams[1] if len(teams) > 1 else "Team B",
                        'agent': None,
                        'stats': {
                            'rating': {'both': None, 'attack': None, 'defend': None},
                            'acs': {'both': None, 'attack': None, 'defend': None},
                            'kills': {'both': None, 'attack': None, 'defend': None},
                            'deaths': {'both': None, 'attack': None, 'defend': None},
                            'assists': {'both': None, 'attack': None, 'defend': None}
                        }
                    })
                
                map_data['player_stats'] = player_stats
                logger.info(f"Extraídos {len(player_stats)} jogadores das informações de matrix para o mapa {map_name}")
        except Exception as e:
            logger.error(f"Erro ao extrair dados de performance para o mapa {map_name}: {e}")
        
        # Adicionar o mapa aos dados e retornar
        result = []
        result.append(map_data)
        return result
        
        # Criar um objeto para representar o mapa (este código nunca será executado)
        # map_tabs = [{'data-game-id': '1', 'text': map_name}]
        
    logger.info(f"Encontradas {len(map_tabs)} abas de mapas")
    
    # Tentar extrair informações dos times do cabeçalho da partida
    teams = []
    team_elements = soup.select('.match-header-vs-team')
    for team in team_elements:
        team_name = team.select_one('.match-header-vs-team-name')
        team_name_text = team_name.get_text(strip=True) if team_name else None
        if team_name_text:
            teams.append(team_name_text)
    
    logger.info(f"Times extraídos do cabeçalho: {teams}")
    
    # Se não conseguimos extrair os times do cabeçalho, tentar outros métodos
    if not teams or len(teams) < 2:
        # Tentar extrair de outros elementos
        match_header = soup.select_one('.match-header')
        if match_header:
            team_names_alt = []
            for team_name_elem in match_header.select('.wf-title-med'):
                team_name_text = team_name_elem.get_text(strip=True)
                if team_name_text and team_name_text not in team_names_alt:
                    team_names_alt.append(team_name_text)
            
            if len(team_names_alt) >= 2:
                teams = team_names_alt[:2]
                logger.info(f"Times extraídos de elementos alternativos: {teams}")
    
    # Extrair a pontuação do cabeçalho (pontuação geral da partida)
    match_scores = [None, None]  # [time1_score, time2_score]
    
    # Buscar no elemento match-header-vs-score
    score_container = soup.select_one('.match-header-vs-score')
    if score_container:
        # Extrair pontuação do vencedor
        winner_score = score_container.select_one('.match-header-vs-score-winner')
        if winner_score:
            try:
                match_scores[0] = int(winner_score.get_text(strip=True))
            except (ValueError, TypeError):
                logger.warning("Não foi possível converter a pontuação do vencedor para inteiro")
        
        # Extrair pontuação do perdedor
        loser_score = score_container.select_one('.match-header-vs-score-loser')
        if loser_score:
            try:
                match_scores[1] = int(loser_score.get_text(strip=True))
            except (ValueError, TypeError):
                logger.warning("Não foi possível converter a pontuação do perdedor para inteiro")
    
    logger.info(f"Pontuações extraídas do cabeçalho: {match_scores}")
    
    # Para cada mapa, extrair detalhes
    for tab in map_tabs:
        # O tab pode ser um elemento BeautifulSoup ou um dicionário (no caso do fallback)
        if isinstance(tab, dict):
            game_id = tab.get('data-game-id')
            tab_text = tab.get('text', '')
        else:
            game_id = tab.get('data-game-id')
            tab_text = tab.get_text(strip=True)
        
        # Se não temos game_id, gerar um
        if not game_id:
            # Usar o índice como ID
            index = map_tabs.index(tab) + 1
            game_id = str(index)
            logger.info(f"Game ID não encontrado, usando índice: {game_id}")
        
        # O texto da aba geralmente está no formato "1Corrode", "2Icebox", etc.
        # Precisamos extrair o nome do mapa removendo o número do início
        map_name = tab_text[1:] if tab_text and len(tab_text) > 1 and tab_text[0].isdigit() else tab_text
        
        # Verificar se o objeto de tab é um dicionário criado pelo fallback
        if isinstance(tab, dict):
            # Para tabs criados pelo fallback, não precisamos encontrar o div
            map_div = None
            using_performance_soup = False
            logger.info(f"Usando mapa fallback: {map_name}")
        else:
            # Encontrar o div correspondente a este mapa
            # Primeiro, procurar na página principal
            map_div = soup.select_one(f'.vm-stats-game[data-game-id="{game_id}"]')
            using_performance_soup = False
            
            # Se não encontrou na página principal, procurar na aba de performance
            if not map_div:
                logger.info(f"Div para o mapa {map_name} (ID: {game_id}) não encontrado na página principal, buscando na aba de performance")
                performance_soup = get_performance_data(match_url)
                if performance_soup:
                    map_div = performance_soup.select_one(f'.vm-stats-game[data-game-id="{game_id}"]')
                    using_performance_soup = True
                    if not map_div:
                        logger.warning(f"Div para o mapa {map_name} (ID: {game_id}) não encontrado na aba de performance")
                else:
                    logger.warning(f"Não foi possível obter dados de performance para o mapa {map_name} (ID: {game_id})")
        
        # Extrair estatísticas dos jogadores da página principal
        map_stats = []
        
        # Tentar extrair estatísticas detalhadas para este mapa usando a função extract_map_stats
        detailed_stats = extract_map_stats(map_div)
        if detailed_stats:
            map_stats = detailed_stats
            logger.info(f"Extraídas estatísticas detalhadas para {len(map_stats)} jogadores no mapa {map_name}")
        
        # Buscar dados de performance para adicionar informações complementares
        # Estes vêm de uma requisição separada feita pelo matrix_extractor
        performance_data = {
            'player_matrix': None,
            'adv_stats': None
        }
        
        # Obter a matriz de jogador vs jogador da aba de performance
        # O matrix_extractor faz a requisição para a aba de performance
        matrix_data = extract_player_matrix(None, game_id, match_url)
        if matrix_data:
            performance_data['player_matrix'] = matrix_data
            logger.info(f"Matriz de jogador vs jogador extraída para o mapa {map_name}")
        else:
            logger.warning(f"Não foi possível extrair matriz de jogador para o mapa {map_name}")
        
        # Se temos dados de matrix, usar os jogadores de lá para complementar estatísticas
        if matrix_data and not map_stats:
            # Extrair jogadores de linha (geralmente time 1)
            row_players = matrix_data.get('row_players', [])
            for player_data in row_players:
                if isinstance(player_data, dict) and 'name' in player_data:
                    map_stats.append({
                        'player': player_data.get('name'),
                        'team': player_data.get('team', teams[0] if len(teams) > 0 else None)
                    })
            
            # Extrair jogadores de coluna (geralmente time 2)
            column_players = matrix_data.get('column_players', [])
            for player_data in column_players:
                if isinstance(player_data, dict) and 'name' in player_data:
                    # Verificar se o jogador já foi adicionado
                    if not any(p.get('player') == player_data.get('name') for p in map_stats):
                        map_stats.append({
                            'player': player_data.get('name'),
                            'team': player_data.get('team', teams[1] if len(teams) > 1 else None)
                        })
            
            logger.info(f"Extraídos {len(map_stats)} jogadores das informações de matrix para o mapa {map_name}")
        
        # Se não encontrou estatísticas detalhadas, tentar apenas extrair informações básicas dos jogadores
        if not map_stats and map_div:
            overview_table = map_div.select_one('table.wf-table-inset.mod-overview')
            if overview_table:
                # Extrair dados de cada jogador
                for row in overview_table.select('tbody tr'):
                    player = {}
                    
                    # Nome e time do jogador
                    player_name_div = row.select_one('.mod-player .text-of')
                    player['player'] = player_name_div.get_text(strip=True) if player_name_div else None
                    
                    team_div = row.select_one('.mod-player .ge-text-light')
                    player['team'] = team_div.get_text(strip=True) if team_div else None
                    
                    map_stats.append(player)
                
                logger.info(f"Extraídos {len(map_stats)} jogadores da tabela mod-overview para o mapa {map_name}")
        
        # Verificar tabela mod-adv-stats (estatísticas avançadas)
        if not map_stats and map_div:
            adv_stats_table = map_div.select_one('table.wf-table-inset.mod-adv-stats')
            if adv_stats_table:
                # Extrair dados de cada jogador
                for row in adv_stats_table.select('tbody tr'):
                    cells = row.select('td')
                    if len(cells) >= 2:
                        player_name = cells[0].get_text(strip=True)
                        team_name = cells[1].get_text(strip=True)
                        
                        map_stats.append({
                            'player': player_name,
                            'team': team_name
                        })
                
                logger.info(f"Extraídos {len(map_stats)} jogadores da tabela mod-adv-stats para o mapa {map_name}")
        
        # Se ainda não temos jogadores, tentar outras tabelas
        if not map_stats and map_div:
            # Verificar se há alguma outra tabela com dados de jogadores
            all_tables = map_div.select('table.wf-table-inset')
            
            for table in all_tables:
                rows = table.select('tbody tr')
                
                # Se a tabela tem linhas, tentar extrair informações
                if rows:
                    for row in rows:
                        cells = row.select('td')
                        
                        # Se tem pelo menos duas células, assumir que as primeiras são jogador e time
                        if len(cells) >= 2:
                            player_name = cells[0].get_text(strip=True)
                            team_name = cells[1].get_text(strip=True)
                            
                            # Se não tem time, tentar inferir pelo contexto
                            if not team_name and teams and len(teams) >= 2:
                                # Determinar o time com base nos padrões já extraídos
                                if len(map_stats) < 5:
                                    team_name = teams[0]
                                else:
                                    team_name = teams[1]
                            
                            # Adicionar apenas se não estiver duplicado
                            if not any(p.get('player') == player_name for p in map_stats):
                                map_stats.append({
                                    'player': player_name,
                                    'team': team_name
                                })
            
            logger.info(f"Extraídos {len(map_stats)} jogadores de tabelas alternativas para o mapa {map_name}")
        
        # Se tudo falhar, usar estrutura mínima com os jogadores da matrix se disponíveis
        if not map_stats and len(teams) >= 2:
            logger.warning(f"Não foi possível extrair estatísticas detalhadas para o mapa {map_name}. Usando estrutura mínima.")
            
            # Se temos dados de matrix, usar nomes reais dos jogadores
            if matrix_data:
                # Nomes do time 1 (linha)
                team1_players = []
                for player in matrix_data.get('row_players', []):
                    if isinstance(player, dict) and 'name' in player:
                        team1_players.append(player.get('name'))
                    elif isinstance(player, str):
                        team1_players.append(player)
                
                # Nomes do time 2 (coluna)
                team2_players = []
                for player in matrix_data.get('column_players', []):
                    if isinstance(player, dict) and 'name' in player:
                        team2_players.append(player.get('name'))
                    elif isinstance(player, str):
                        team2_players.append(player)
                
                # Preencher com placeholders se necessário
                while len(team1_players) < 5:
                    team1_players.append(f"Player{len(team1_players)+1}")
                
                while len(team2_players) < 5:
                    team2_players.append(f"Player{len(team2_players)+6}")
                
                # Criar registros para cada jogador
                for i, player_name in enumerate(team1_players[:5]):
                    map_stats.append({
                        'player': player_name,
                        'team': teams[0]
                    })
                
                for i, player_name in enumerate(team2_players[:5]):
                    map_stats.append({
                        'player': player_name,
                        'team': teams[1]
                    })
            else:
                # Usar placeholders genéricos se não temos nada
                map_stats = [
                    {'player': 'Player1', 'team': teams[0]},
                    {'player': 'Player2', 'team': teams[0]},
                    {'player': 'Player3', 'team': teams[0]},
                    {'player': 'Player4', 'team': teams[0]},
                    {'player': 'Player5', 'team': teams[0]},
                    {'player': 'Player6', 'team': teams[1]},
                    {'player': 'Player7', 'team': teams[1]},
                    {'player': 'Player8', 'team': teams[1]},
                    {'player': 'Player9', 'team': teams[1]},
                    {'player': 'Player10', 'team': teams[1]},
                ]
        
        # Extrair pontuações dos times para este mapa
        team_scores = [None, None]
        
        # Procurar na página principal pelo cabeçalho do mapa com este game_id
        # Os cabeçalhos com vm-stats-game-header estão na página principal, não na aba de performance
        vm_stats_games = soup.select('.vm-stats-game')
        target_game = None
        for game in vm_stats_games:
            if game.get('data-game-id') == game_id:
                target_game = game
                break
                
        if target_game:
            game_header = target_game.select_one('.vm-stats-game-header')
            if game_header:
                logger.debug(f"Encontrou vm-stats-game-header para mapa {map_name} (ID: {game_id})")
                
                # Extrair pontuações dos elementos .score
                score_elements = game_header.select('.score')
                for i, score_elem in enumerate(score_elements):
                    score_text = score_elem.get_text(strip=True)
                    try:
                        if i < len(team_scores):
                            team_scores[i] = int(score_text)
                    except (ValueError, TypeError):
                        pass
                
                logger.debug(f"Pontuações extraídas do cabeçalho do mapa: {team_scores}")
                
                # Também extrair nomes de times se necessário
                if not teams or len(teams) < 2:
                    map_team_names = []
                    for team_div in game_header.select('.team'):
                        team_name_div = team_div.select_one('.team-name')
                        if team_name_div:
                            team_name = team_name_div.get_text(strip=True)
                            if team_name:
                                map_team_names.append(team_name)
                    
                    if len(map_team_names) >= 2:
                        teams = map_team_names
                        logger.debug(f"Times extraídos do cabeçalho do mapa: {teams}")
        
        # Se não conseguiu extrair pontuações do cabeçalho, tentar outros métodos
        if team_scores[0] is None or team_scores[1] is None:
            # Buscar em outros elementos de pontuação no mapa
            extracted_scores = []
            
            if map_div is not None:
                score_elements = map_div.select('.score, .mod-t, .mod-ct, .mod-score')
                if score_elements:
                    for score_elem in score_elements:
                        score_text = score_elem.get_text(strip=True)
                        try:
                            score = int(score_text)
                            extracted_scores.append(score)
                        except (ValueError, TypeError):
                            pass
            
            # Tentar nas abas
            if not extracted_scores or len(extracted_scores) < 2:
                score_container = soup.select_one(f'.vm-stats-gamesnav-item[data-game-id="{game_id}"]')
                if score_container:
                    score_items = score_container.select('.team-score, .score')
                    for score_item in score_items:
                        score_text = score_item.get_text(strip=True)
                        try:
                            score = int(score_text)
                            extracted_scores.append(score)
                        except (ValueError, TypeError):
                            pass
            
            # Usar as pontuações extraídas se houver pelo menos duas
            if len(extracted_scores) >= 2:
                team_scores[0] = extracted_scores[0]
                team_scores[1] = extracted_scores[1]
        
        # Extrair informações sobre os rounds do mapa
        rounds_data = []
        vlr_rounds = soup.select('.vlr-rounds')
        
        # Encontrar o vlr-rounds correspondente ao mapa atual
        target_vlr_rounds = None
        if vlr_rounds:
            # Se houver apenas um elemento vlr-rounds, usamos ele
            if len(vlr_rounds) == 1:
                target_vlr_rounds = vlr_rounds[0]
            # Se houver vários, tentamos encontrar o que corresponde ao game_id atual
            elif len(vlr_rounds) > 1:
                # Tenta encontrar o div de rounds correspondente a este mapa
                # Assume que a ordem dos vlr-rounds corresponde à ordem dos mapas
                if game_id and game_id.isdigit():
                    map_index = int(game_id) - 1
                    if map_index < len(vlr_rounds):
                        target_vlr_rounds = vlr_rounds[map_index]
                    else:
                        target_vlr_rounds = vlr_rounds[0]
                else:
                    # Se não conseguir determinar, usa o primeiro
                    target_vlr_rounds = vlr_rounds[0]
        
        if target_vlr_rounds:
            # Extrair os times
            team_elements = target_vlr_rounds.select('.team')
            round_teams = []
            for team_elem in team_elements:
                team_name = team_elem.get_text(strip=True)
                team_img = None
                img_elem = team_elem.select_one('img')
                if img_elem:
                    team_img = img_elem.get('src')
                    if team_img and team_img.startswith('//'):
                        team_img = 'https:' + team_img
                round_teams.append({
                    'name': team_name,
                    'img': team_img
                })
            
            # Extrair os rounds
            round_cols = target_vlr_rounds.select('.vlr-rounds-row-col:not(.mod-spacing)')
            
            for col in round_cols:
                # Pular a coluna de rótulos de times
                if not col.select_one('.rnd-num'):
                    continue
                
                round_num = col.select_one('.rnd-num')
                if not round_num:
                    continue
                
                round_data = {
                    'round_number': round_num.get_text(strip=True),
                    'title': col.get('title', ''),
                    'winner': None,
                    'winner_team': None,
                    'win_type': None,
                    'win_side': None
                }
                
                # Procurar pelo quadrado vencedor
                win_square = col.select_one('.rnd-sq.mod-win')
                if win_square:
                    # Determinar o time vencedor
                    winner_index = None
                    if 'mod-t' in win_square.get('class', []):
                        round_data['win_side'] = 'attack'
                        winner_index = 0 if win_square == col.select('.rnd-sq')[0] else 1
                    elif 'mod-ct' in win_square.get('class', []):
                        round_data['win_side'] = 'defense'
                        winner_index = 0 if win_square == col.select('.rnd-sq')[0] else 1
                    
                    # Definir o índice do vencedor e o nome do time vencedor
                    if winner_index is not None:
                        round_data['winner'] = winner_index
                        if winner_index < len(teams):
                            round_data['winner_team'] = teams[winner_index]
                    
                    # Extrair o tipo de vitória com base na imagem
                    img_elem = win_square.select_one('img')
                    if img_elem:
                        img_src = img_elem.get('src', '')
                        if 'elim' in img_src:
                            round_data['win_type'] = 'elimination'
                        elif 'boom' in img_src:
                            round_data['win_type'] = 'spike_detonation'
                        elif 'defuse' in img_src:
                            round_data['win_type'] = 'spike_defuse'
                        elif 'time' in img_src:
                            round_data['win_type'] = 'time_out'
                
                rounds_data.append(round_data)
            
            logger.debug(f"Extraídos {len(rounds_data)} rounds para o mapa {map_name}")
        else:
            logger.debug(f"Não foi possível encontrar dados de rounds para o mapa {map_name}")
        
        # Inicializar dados do mapa
        map_data = {
            'game_id': game_id,
            'map_name': map_name,
            'teams': [
                {'name': teams[0], 'score': team_scores[0]} if len(teams) > 0 else {'name': None, 'score': None},
                {'name': teams[1], 'score': team_scores[1]} if len(teams) > 1 else {'name': None, 'score': None}
            ],
            'stats': map_stats,
            'rounds': rounds_data,
            'performance': performance_data
        }
        
        # Garantir que os campos teams e stats estão presentes
        if 'teams' not in map_data:
            map_data['teams'] = [
                {'name': teams[0], 'score': None} if len(teams) > 0 else {'name': None, 'score': None},
                {'name': teams[1], 'score': None} if len(teams) > 1 else {'name': None, 'score': None}
            ]
        
        if 'stats' not in map_data:
            map_data['stats'] = map_stats
        
        match_maps.append(map_data)
    
    return match_maps

# Alias for compatibility with imports
def vlr_match_details(match_url):
    return get_match_details(match_url)


