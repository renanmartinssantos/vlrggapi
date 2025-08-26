import requests
import logging
from bs4 import BeautifulSoup
import re
from utils.utils import headers

def get_performance_data(match_url, game_id=None):
    """
    Obtém dados de performance específicos de um URL de partida
    Adiciona automaticamente os parâmetros ?game=all&tab=performance
    """
    logger = logging.getLogger("scraper")
    
    # Garantir que a URL tenha os parâmetros necessários para a aba de performance
    if "?" in match_url:
        if "tab=performance" not in match_url:
            url = f"{match_url}&tab=performance"
        else:
            url = match_url
    else:
        url = f"{match_url}?tab=performance"
        
    # Adicionar game=all se não houver game específico
    if "game=" not in url:
        url = f"{url}&game=all"
    
    logger.debug(f"Buscando dados de performance da URL: {url}")
    
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, 'html.parser')
        else:
            logger.error(f"Erro ao buscar dados de performance. Status code: {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"Exceção ao buscar dados de performance: {str(e)}")
        return None

def extract_player_matrix(map_div, game_id, match_url=None):
    """
    Extrai a matriz de confrontos entre jogadores para um mapa específico
    
    Args:
        map_div: O elemento BeautifulSoup contendo os dados do mapa. Se None, tentará buscar via match_url.
        game_id: O ID do mapa para o qual extrair os dados de matriz.
        match_url: URL opcional da partida, para buscar dados quando map_div não está disponível.
    """
    import logging
    
    logger = logging.getLogger("scraper")
    
    matrix_data = {
        'game_id': game_id,
        'column_players': [],  # jogadores nas colunas (time 1)
        'row_players': [],     # jogadores nas linhas (time 2)
        'matchups': [],        # dados de confronto entre jogadores
        'adv_stats': []        # estatísticas avançadas (multi-kills, clutches, etc)
    }
    
    logger.debug(f"Procurando matrix para game_id: {game_id}")
    
    # Verifica se estamos recebendo um HTML como string ou um objeto BeautifulSoup
    if isinstance(map_div, str):
        map_div = BeautifulSoup(map_div, 'html.parser')
    
    # Se não temos map_div, mas temos a URL da partida, buscar os dados de performance
    if map_div is None and match_url:
        logger.debug(f"Map_div não fornecido, buscando dados de performance para game_id={game_id}")
        
        # Construir URL com os parâmetros corretos para a aba de performance e o mapa específico
        if game_id:
            performance_url = f"{match_url}?tab=performance&game={game_id}"
        else:
            performance_url = f"{match_url}?tab=performance&game=all"
            
        logger.debug(f"Buscando dados de performance em: {performance_url}")
        
        try:
            resp = requests.get(performance_url, headers=headers)
            if resp.status_code == 200:
                performance_soup = BeautifulSoup(resp.text, 'html.parser')
                map_div = performance_soup.select_one(f'.vm-stats-game[data-game-id="{game_id}"]')
                if not map_div:
                    # Se não encontrou o mapa específico, tenta encontrar qualquer vm-stats-game
                    map_div = performance_soup.select_one('.vm-stats-game')
                    if not map_div:
                        logger.error(f"Não foi possível encontrar a div do mapa na página de performance")
                        return matrix_data
            else:
                logger.error(f"Erro ao buscar dados de performance. Status code: {resp.status_code}")
                return matrix_data
        except Exception as e:
            logger.error(f"Exceção ao buscar dados de performance: {str(e)}")
            return matrix_data
    
    # Procura a div do jogo com o game_id correto
    game_div = None
    
    # Tenta encontrar a div vm-stats-game específica
    for div in map_div.find_all('div', {'class': 'vm-stats-game'}):
        if div.get('data-game-id') == game_id:
            game_div = div
            logger.debug(f"Encontrou vm-stats-game com data-game-id={game_id}")
            break
    
    # Se não encontrou especificamente, use o que foi passado
    if not game_div:
        game_div = map_div
        logger.debug(f"Usando div passada como parâmetro")
    
    # Busca adicional para jogadores quando não os encontra nas tabelas
    # Isso é útil quando temos jogadores na página mas não na matriz
    fallback_players = []
    player_name_divs = game_div.select('.mod-player .text-of')
    player_team_divs = game_div.select('.mod-player .ge-text-light')
    
    if player_name_divs and len(player_name_divs) > 0:
        logger.debug(f"Encontrados {len(player_name_divs)} jogadores via fallback")
        
        for i, name_div in enumerate(player_name_divs):
            player_name = name_div.get_text(strip=True)
            player_team = player_team_divs[i].get_text(strip=True) if i < len(player_team_divs) else None
            
            if player_name:
                fallback_players.append({
                    'name': player_name,
                    'team': player_team,
                    'team_logo': None
                })
    
    # Encontrar todas as tabelas que podem ser matrizes
    all_tables = []
    
    # Abordagem 1: Procurar diretamente por tabelas mod-matrix
    for table in game_div.find_all('table'):
        classes = table.get('class', [])
        if not isinstance(classes, list):
            classes = classes.split() if classes else []
        
        if 'mod-matrix' in classes:
            all_tables.append(table)
            logger.debug(f"Encontrou tabela diretamente: {' '.join(classes)}")
    
    # Abordagem 2: Procurar em divs com overflow
    overflow_divs = []
    for div in game_div.find_all('div'):
        style = div.get('style')
        if style and 'overflow-x: auto' in style:
            overflow_divs.append(div)
    
    for div in overflow_divs:
        for table in div.find_all('table'):
            classes = table.get('class', [])
            if not isinstance(classes, list):
                classes = classes.split() if classes else []
            
            if 'mod-matrix' in classes:
                all_tables.append(table)
                logger.debug(f"Encontrou tabela em div overflow: {' '.join(classes)}")
    
    # Abordagem 3: Procurar tabelas com classes específicas
    for table in game_div.find_all('table', class_=lambda c: c and ('mod-matrix' in c or 'wf-table-inset' in c)):
        if table not in all_tables:
            all_tables.append(table)
            logger.debug(f"Encontrou tabela com classe específica: {table.get('class')}")
    
    logger.debug(f"Total de tabelas encontradas: {len(all_tables)}")
    
    # Filtrar para encontrar as tabelas específicas
    matrix_table = None  # mod-normal (Kills/Deaths)
    fk_fd_table = None   # mod-fkfd (First Kills/First Deaths)
    op_table = None      # mod-op (Operator Kills)
    
    for table in all_tables:
        classes = table.get('class', [])
        if not isinstance(classes, list):
            classes = classes.split() if classes else []
        classes_str = ' '.join(classes)
        
        if 'mod-normal' in classes:
            matrix_table = table
            logger.debug(f"Encontrou tabela mod-normal")
        elif 'mod-fkfd' in classes:
            fk_fd_table = table
            logger.debug(f"Encontrou tabela mod-fkfd")
        elif 'mod-op' in classes:
            op_table = table
            logger.debug(f"Encontrou tabela mod-op")
    
    # Se não encontrou mod-normal específica, tenta uma heurística
    if not matrix_table and all_tables:
        # Tenta encontrar uma tabela que não seja mod-fkfd nem mod-op
        for table in all_tables:
            classes = table.get('class', [])
            if not isinstance(classes, list):
                classes = classes.split() if classes else []
            
            if 'mod-fkfd' not in classes and 'mod-op' not in classes:
                matrix_table = table
                logger.debug(f"Usando tabela como mod-normal por exclusão: {' '.join(classes)}")
                break
        
        # Se ainda não encontrou, usa a primeira tabela
        if not matrix_table:
            matrix_table = all_tables[0]
            logger.debug(f"Usando primeira tabela encontrada como fallback")
    
    # Se mesmo assim não temos tabela, retorna dados vazios
    if not matrix_table:
        logger.debug(f"Nenhuma tabela matrix encontrada para game_id: {game_id}")
        
        # Se temos fallback_players, vamos usá-los
        if fallback_players:
            logger.debug(f"Usando fallback players ({len(fallback_players)})")
            
            # Dividir jogadores entre times com base no team
            team_players = {}
            for player in fallback_players:
                team = player.get('team')
                if team not in team_players:
                    team_players[team] = []
                team_players[team].append(player)
            
            # Se temos dois times, podemos criar uma estrutura básica
            if len(team_players) == 2:
                teams = list(team_players.keys())
                matrix_data['column_players'] = team_players[teams[0]]
                matrix_data['row_players'] = team_players[teams[1]]
                logger.debug(f"Criada estrutura com {len(matrix_data['column_players'])} jogadores de coluna e {len(matrix_data['row_players'])} jogadores de linha")
            # Se temos apenas um time ou mais de dois, distribuir entre colunas e linhas
            elif fallback_players:
                half = len(fallback_players) // 2
                matrix_data['column_players'] = fallback_players[:half]
                matrix_data['row_players'] = fallback_players[half:]
                logger.debug(f"Distribuídos jogadores: {len(matrix_data['column_players'])} nas colunas e {len(matrix_data['row_players'])} nas linhas")
        
        return matrix_data
    
    # Extrair jogadores das colunas (cabeçalho)
    header_row = matrix_table.find('tr')  # Primeira linha (cabeçalho)
    if not header_row:
        logger.debug(f"Tabela não contém linhas")
        return matrix_data
    
    header_cells = header_row.find_all('td')
    
    # Primeira célula é vazia, as outras contêm os jogadores das colunas
    if len(header_cells) > 1:
        for cell in header_cells[1:]:  # Pula a primeira célula vazia
            player_info = {'name': None, 'team': None, 'team_logo': None}
            
                # Tenta extrair informações do jogador usando diferentes abordagens
            
            # Abordagem 1: Busca a div da equipe
            team_div = cell.find('div', class_='team')
            if team_div:
                # Encontra a div principal que contém o nome do jogador
                player_div = team_div.find('div', recursive=False)
                if player_div:
                    # Extrai o texto direto desta div, sem incluir o texto da div team-tag
                    player_text = player_div.contents[0]
                    if isinstance(player_text, str):
                        player_name = player_text.strip()
                        if player_name:
                            player_info['name'] = player_name
                
                # Tag da equipe
                team_tag = team_div.find('div', class_='team-tag')
                if team_tag:
                    team_name = team_tag.get_text(strip=True)
                    if team_name:
                        player_info['team'] = team_name                # Logo da equipe
                team_logo = team_div.find('img', class_='team-logo')
                if team_logo and team_logo.get('src'):
                    logo_src = team_logo.get('src')
                    if logo_src.startswith('//'):
                        player_info['team_logo'] = 'https:' + logo_src
                    else:
                        player_info['team_logo'] = logo_src
            
            # Abordagem 2: Se não encontrou nome na abordagem 1, busca texto diretamente
            if not player_info['name']:
                player_text = cell.get_text(strip=True)
                if player_text:
                    player_info['name'] = player_text
            
            # Só adiciona se encontrou pelo menos o nome
            if player_info['name']:
                matrix_data['column_players'].append(player_info)
                logger.debug(f"Extraído jogador de coluna: {player_info['name']}")
            else:
                logger.debug(f"Célula de coluna sem nome de jogador")
        
        logger.debug(f"Extraídos {len(matrix_data['column_players'])} jogadores de coluna")
    
    # Extrair jogadores das linhas e confrontos (linhas de dados)
    data_rows = matrix_table.find_all('tr')[1:]  # Pula a linha de cabeçalho
    for row in data_rows:
        cells = row.find_all('td')
        if not cells or len(cells) <= 1:  # Precisa de pelo menos a célula do jogador e uma de confronto
            continue
        
        # Primeira célula contém o jogador da linha
        player_cell = cells[0]
        player_info = {'name': None, 'team': None, 'team_logo': None}
        
        # Abordagem 1: Busca a div da equipe
        team_div = player_cell.find('div', class_='team')
        if team_div:
            # Encontra a div principal que contém o nome do jogador
            player_div = team_div.find('div', recursive=False)
            if player_div:
                # Extrai o texto direto desta div, sem incluir o texto da div team-tag
                player_text = player_div.contents[0]
                if isinstance(player_text, str):
                    player_name = player_text.strip()
                    if player_name:
                        player_info['name'] = player_name
            
            # Tag da equipe
            team_tag = team_div.find('div', class_='team-tag')
            if team_tag:
                team_name = team_tag.get_text(strip=True)
                if team_name:
                    player_info['team'] = team_name
            
            # Logo da equipe
            team_logo = team_div.find('img', class_='team-logo')
            if team_logo and team_logo.get('src'):
                logo_src = team_logo.get('src')
                if logo_src.startswith('//'):
                    player_info['team_logo'] = 'https:' + logo_src
                else:
                    player_info['team_logo'] = logo_src
        
        # Abordagem 2: Se não encontrou nome na abordagem 1, busca texto diretamente
        if not player_info['name']:
            player_text = player_cell.get_text(strip=True)
            if player_text:
                player_info['name'] = player_text
        
        # Só continua se encontrou pelo menos o nome do jogador
        if not player_info['name']:
            logger.debug(f"Linha sem nome de jogador, pulando")
            continue
        
        matrix_data['row_players'].append(player_info)
        logger.debug(f"Extraído jogador de linha: {player_info['name']}")
        
        # Extrair dados de confronto
        matchups_row = []
        for i, cell in enumerate(cells[1:]):  # Pula a primeira célula (jogador da linha)
            if i >= len(matrix_data['column_players']):
                logger.debug(f"Índice de coluna {i} excede o número de jogadores de coluna {len(matrix_data['column_players'])}")
                continue
            
            column_player = matrix_data['column_players'][i]['name']
            row_player = player_info['name']
            
            matchup = {
                'row_player': row_player,
                'column_player': column_player,
                'value1': None,  # Primeiro valor (não necessariamente kills)
                'value2': None,  # Segundo valor (não necessariamente deaths)
                'diff': None     # Diferença entre os valores
            }
            
            # Busca a div com flex para stats (várias abordagens)
            stats_div = None
            
            # Abordagem 1: Div com estilo display: flex
            for div in cell.find_all('div', recursive=False):
                style = div.get('style', '')
                if 'display: flex' in style:
                    stats_div = div
                    break
            
            # Abordagem 2: Se não encontrou, busca divs com classes específicas
            if not stats_div:
                stats_div = cell.find('div', class_='stats-container')
            
            # Abordagem 3: Busca divs que contenham stats-sq
            if not stats_div:
                for div in cell.find_all('div'):
                    if div.find('div', class_='stats-sq'):
                        stats_div = div
                        break
            
            # Extrai os valores se encontrou a div de estatísticas
            if stats_div:
                stats_squares = stats_div.find_all('div', class_='stats-sq')
                if len(stats_squares) >= 3:
                    # Os valores nas stats-sq são respectivamente:
                    # 1. Primeiro valor (geralmente kills do jogador da linha para o da coluna)
                    # 2. Segundo valor (geralmente kills do jogador da coluna para o da linha)
                    # 3. Diferença entre os valores (com sinal + ou -)
                    value1 = stats_squares[0].get_text(strip=True)
                    value2 = stats_squares[1].get_text(strip=True)
                    diff = stats_squares[2].get_text(strip=True)
                    
                    if value1:
                        matchup['value1'] = value1
                    if value2:
                        matchup['value2'] = value2
                    if diff:
                        matchup['diff'] = diff
            
            # Abordagem alternativa: se ainda não temos valores, tentar extrair diretamente da célula
            if not matchup['value1'] and not matchup['value2']:
                # Tentar encontrar qualquer div com texto numérico
                for div in cell.find_all('div'):
                    text = div.get_text(strip=True)
                    if text and text.replace('+', '').replace('-', '').isdigit():
                        # Se parece com um valor de diferença (+2, -3, etc)
                        if (text.startswith('+') or text.startswith('-')) and matchup['diff'] is None:
                            matchup['diff'] = text
                        # Se é um número simples, pode ser um valor de kills
                        elif matchup['value1'] is None:
                            matchup['value1'] = text
                        elif matchup['value2'] is None:
                            matchup['value2'] = text
                
                # Se encontramos apenas o valor1 mas não o diff, vamos definir um diff padrão
                if matchup['value1'] and not matchup['diff']:
                    matchup['diff'] = f"+{matchup['value1']}"
            
            matchups_row.append(matchup)
        
        # Só adiciona se extraiu dados de confronto
        if matchups_row:
            matrix_data['matchups'].append(matchups_row)
    
    logger.debug(f"Extraídos {len(matrix_data['row_players'])} jogadores de linha e seus confrontos")
    
    # Extrair dados das tabelas adicionais (FK/FD e OP)
    if fk_fd_table:
        logger.debug(f"Extraindo dados da tabela mod-fkfd")
        matrix_data['fk_fd'] = extract_matrix_data(fk_fd_table, matrix_data['row_players'], matrix_data['column_players'])
    
    if op_table:
        logger.debug(f"Extraindo dados da tabela mod-op")
        matrix_data['op_kills'] = extract_matrix_data(op_table, matrix_data['row_players'], matrix_data['column_players'])
    
    # Verificar se temos dados de matriz, se não, usar a abordagem de fallback
    if (not matrix_data['column_players'] or not matrix_data['row_players']) and fallback_players:
        logger.debug(f"Matriz vazia, usando fallback players")
        
        # Dividir jogadores entre times com base no team
        team_players = {}
        for player in fallback_players:
            team = player.get('team')
            if team not in team_players:
                team_players[team] = []
            team_players[team].append(player)
        
        # Se temos dois times, podemos criar uma estrutura básica
        if len(team_players) == 2:
            teams = list(team_players.keys())
            matrix_data['column_players'] = team_players[teams[0]]
            matrix_data['row_players'] = team_players[teams[1]]
            logger.debug(f"Criada estrutura com {len(matrix_data['column_players'])} jogadores de coluna e {len(matrix_data['row_players'])} jogadores de linha")
        # Se temos apenas um time ou mais de dois, distribuir entre colunas e linhas
        elif fallback_players:
            half = len(fallback_players) // 2
            matrix_data['column_players'] = fallback_players[:half]
            matrix_data['row_players'] = fallback_players[half:]
            logger.debug(f"Distribuídos jogadores: {len(matrix_data['column_players'])} nas colunas e {len(matrix_data['row_players'])} nas linhas")
    
    # Gerar o formato players_matchup solicitado
    logger.debug(f"Gerando formato players_matchup")
    
    # Processar cada matchup do formato original para o novo formato
    for i, row_player in enumerate(matrix_data['row_players']):
        for j, column_player in enumerate(matrix_data['column_players']):
            # Encontrar o matchup nos dados originais, se existir
            value1 = None
            value2 = None
            diff = None
            
            if i < len(matrix_data['matchups']) and j < len(matrix_data['matchups'][i]):
                matchup = matrix_data['matchups'][i][j]
                value1 = matchup.get('value1')
                value2 = matchup.get('value2')
                diff = matchup.get('diff')
        
    
    # Extrair dados da tabela de estatísticas avançadas
    extract_advanced_stats(map_div, game_id, matrix_data)
    
    return matrix_data

def extract_matrix_data(table, row_players, column_players):
    """
    Extrai dados de uma tabela de matriz específica (FK/FD ou OP kills)
    """
    import logging
    logger = logging.getLogger("scraper")
    
    matrix_data = {
        'matchups': []
    }
    
    # Verifica se temos os jogadores necessários
    if not row_players or not column_players:
        logger.debug(f"Faltam jogadores para extrair matriz: row_players={len(row_players) if row_players else 0}, column_players={len(column_players) if column_players else 0}")
        return matrix_data
    
    # Processa cada linha (exceto o cabeçalho)
    data_rows = table.find_all('tr')[1:] if table else []
    logger.debug(f"Processando {len(data_rows)} linhas na tabela secundária")
    
    for i, row in enumerate(data_rows):
        if i >= len(row_players):
            logger.debug(f"Índice de linha {i} excede o número de jogadores de linha {len(row_players)}")
            continue
        
        matchups_row = []
        cells = row.find_all('td')
        
        # Pula a primeira célula (contém o jogador da linha)
        matchup_cells = cells[1:] if cells else []
        
        for j, cell in enumerate(matchup_cells):
            if j >= len(column_players):
                logger.debug(f"Índice de coluna {j} excede o número de jogadores de coluna {len(column_players)}")
                continue
                
            row_player_name = row_players[i]['name']
            column_player_name = column_players[j]['name']
            
            matchup = {
                'row_player': row_player_name,
                'column_player': column_player_name,
                'value1': None,
                'value2': None,
                'diff': None
            }
            
            # Busca a div com flex para stats (várias abordagens)
            stats_div = None
            
            # Abordagem 1: Div com estilo display: flex
            for div in cell.find_all('div', recursive=False):
                style = div.get('style', '')
                if 'display: flex' in style:
                    stats_div = div
                    break
            
            # Abordagem 2: Se não encontrou, busca divs com classes específicas
            if not stats_div:
                stats_div = cell.find('div', class_='stats-container')
            
            # Abordagem 3: Busca divs que contenham stats-sq
            if not stats_div:
                for div in cell.find_all('div'):
                    if div.find('div', class_='stats-sq'):
                        stats_div = div
                        break
            
            # Extrai os valores se encontrou a div de estatísticas
            if stats_div:
                stats_squares = stats_div.find_all('div', class_='stats-sq')
                if len(stats_squares) >= 3:
                    # Os valores nas stats-sq são respectivamente:
                    # 1. Primeiro valor 
                    # 2. Segundo valor 
                    # 3. Diferença entre os valores (com sinal + ou -)
                    value1 = stats_squares[0].get_text(strip=True)
                    value2 = stats_squares[1].get_text(strip=True)
                    diff = stats_squares[2].get_text(strip=True)
                    
                    if value1:
                        matchup['value1'] = value1
                    if value2:
                        matchup['value2'] = value2
                    if diff:
                        matchup['diff'] = diff
            
            # Abordagem alternativa: se ainda não temos valores, tentar extrair diretamente da célula
            if not matchup['value1'] and not matchup['value2']:
                # Tentar encontrar qualquer div com texto numérico
                for div in cell.find_all('div'):
                    text = div.get_text(strip=True)
                    if text and text.replace('+', '').replace('-', '').isdigit():
                        # Se parece com um valor de diferença (+2, -3, etc)
                        if (text.startswith('+') or text.startswith('-')) and matchup['diff'] is None:
                            matchup['diff'] = text
                        # Se é um número simples, pode ser um valor de kills
                        elif matchup['value1'] is None:
                            matchup['value1'] = text
                        elif matchup['value2'] is None:
                            matchup['value2'] = text
                
                # Se encontramos apenas o valor1 mas não o diff, vamos definir um diff padrão
                if matchup['value1'] and not matchup['diff']:
                    matchup['diff'] = f"+{matchup['value1']}"
            
            matchups_row.append(matchup)
        
        # Só adiciona se extraiu dados de confronto
        if matchups_row:
            matrix_data['matchups'].append(matchups_row)
    
    return matrix_data

def extract_advanced_stats(map_div, game_id, matrix_data):
    """
    Extrai dados da tabela de estatísticas avançadas (multi-kills, clutches, etc)
    """
    import logging
    logger = logging.getLogger("scraper")
    
    # Verifica se estamos recebendo um HTML como string ou um objeto BeautifulSoup
    if isinstance(map_div, str):
        map_div = BeautifulSoup(map_div, 'html.parser')
    
    # Procura a div do jogo com o game_id correto
    game_div = None
    
    # Tenta encontrar a div vm-stats-game específica
    for div in map_div.find_all('div', {'class': 'vm-stats-game'}):
        if div.get('data-game-id') == game_id:
            game_div = div
            logger.debug(f"Encontrou vm-stats-game com data-game-id={game_id} para adv stats")
            break
    
    # Se não encontrou especificamente, use o que foi passado
    if not game_div:
        game_div = map_div
        logger.debug(f"Usando div passada como parâmetro para adv stats")
    
    # Procurar a tabela de estatísticas avançadas
    adv_stats_table = game_div.find('table', {'class': 'wf-table-inset mod-adv-stats'})
    
    if not adv_stats_table:
        logger.debug(f"Tabela de estatísticas avançadas não encontrada para game_id: {game_id}")
        return
    
    logger.debug(f"Encontrou tabela de estatísticas avançadas para game_id: {game_id}")
    
    # Obter as colunas da tabela (cabeçalho)
    header_row = adv_stats_table.find('tr')
    if not header_row:
        logger.debug(f"Tabela de estatísticas avançadas não contém linhas de cabeçalho")
        return
    
    header_cells = header_row.find_all('th')
    column_names = []
    
    # Primeira e segunda colunas geralmente são vazias ou contêm informações do jogador
    for i, cell in enumerate(header_cells):
        if i < 2:  # Pular as duas primeiras colunas (jogador e agente)
            continue
        
        column_name = cell.get_text(strip=True)
        column_names.append(column_name)
    
    logger.debug(f"Colunas encontradas: {', '.join(column_names)}")
    
    # Processar cada linha (jogador)
    data_rows = adv_stats_table.find_all('tr')[1:]  # Pular a linha de cabeçalho
    for row in data_rows:
        cells = row.find_all('td')
        if len(cells) < 3:  # Precisamos de pelo menos jogador, agente e uma stat
            continue
        
        # Extrair informações do jogador
        player_cell = cells[0]
        agent_cell = cells[1]
        
        player_info = {'name': None, 'team': None, 'team_logo': None, 'agent': None}
        
        # Extrair o nome do jogador e equipe
        team_div = player_cell.find('div', class_='team')
        if team_div:
            # Nome do jogador
            player_div = team_div.find('div', recursive=False)
            if player_div:
                player_text = player_div.get_text(strip=True)
                player_info['name'] = player_text
            
            # Tag da equipe
            team_tag = team_div.find('div', class_='team-tag')
            if team_tag:
                team_name = team_tag.get_text(strip=True)
                player_info['team'] = team_name
            
            # Logo da equipe
            team_logo = team_div.find('img', class_='team-logo')
            if team_logo and team_logo.get('src'):
                logo_src = team_logo.get('src')
                if logo_src.startswith('//'):
                    player_info['team_logo'] = 'https:' + logo_src
                else:
                    player_info['team_logo'] = logo_src
        
        # Extrair o agente
        agent_img = agent_cell.find('img')
        if agent_img and agent_img.get('src'):
            agent_src = agent_img.get('src')
            agent_name = agent_src.split('/')[-1].split('.')[0] if '/' in agent_src else None
            player_info['agent'] = agent_name
        
        # Se não conseguimos extrair o nome do jogador, não continua
        if not player_info['name']:
            continue
        
        # Extrair estatísticas avançadas
        player_stats = {'game_id': game_id, 'player': player_info}
        
        for i, cell in enumerate(cells[2:]):  # Pular as duas primeiras colunas (jogador e agente)
            if i >= len(column_names):
                break
            
            column_name = column_names[i]
            
            # Extrair o valor da estatística
            stat_value = None
            stats_sq = cell.find('div', class_='stats-sq')
            if stats_sq:
                stat_text = stats_sq.get_text(strip=True)
                if stat_text and stat_text != "":
                    stat_value = stat_text
            
            # Extrair detalhes adicionais para estatísticas com popups
            details = []
            if stats_sq and 'wf-popable' in stats_sq.get('class', []):
                details_div = stats_sq.find('div', class_='wf-popable-contents')
                if details_div:
                    for round_div in details_div.find_all('div', style=lambda s: s and 'margin-top: 10px' in s):
                        round_info = {'round': None, 'opponents': []}
                        
                        # Extrair o número da rodada
                        round_number_div = round_div.find('div', style=lambda s: s and 'white-space: nowrap' in s)
                        if round_number_div:
                            round_span = round_number_div.find('span')
                            if round_span:
                                round_info['round'] = round_span.get_text(strip=True)
                        
                        # Extrair os oponentes
                        for opponent_div in round_div.find_all('div', style=lambda s: s and 'display: flex' in s):
                            opponent_img = opponent_div.find('img')
                            opponent_text = opponent_div.get_text(strip=True) if opponent_div else None
                            
                            if opponent_img and opponent_text:
                                agent_src = opponent_img.get('src')
                                agent_name = agent_src.split('/')[-1].split('.')[0] if '/' in agent_src else None
                                opponent_info = {
                                    'agent': agent_name,
                                    'name': opponent_text
                                }
                                round_info['opponents'].append(opponent_info)
                        
                        details.append(round_info)
            
            # Adicionar estatística ao jogador
            player_stats[column_name] = {
                'value': stat_value if stat_value else "0",
                'details': details if details else []
            }
        
        # Adicionar estatísticas do jogador aos dados da matriz
        matrix_data['adv_stats'].append(player_stats)
    
    logger.debug(f"Extraídas estatísticas avançadas para {len(matrix_data['adv_stats'])} jogadores")
