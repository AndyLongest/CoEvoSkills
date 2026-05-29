"""
Civ6 District Adjacency Optimizer - Core Utils
"""

import json
import re
import math
from collections import defaultdict

# =============================================================================
# Hex Grid Utilities (odd-r offset coordinates)
# =============================================================================

def get_neighbors(x: int, y: int):
    """Get all 6 neighboring hex coordinates."""
    if y % 2 == 0:  # even row
        directions = [(1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1)]
    else:  # odd row - shifted right
        directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (0, 1), (1, 1)]
    return [(x + dx, y + dy) for dx, dy in directions]


def hex_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    """Calculate hex distance using cube coordinate conversion."""
    def offset_to_cube(col, row):
        cx = col - (row - (row & 1)) // 2
        cz = row
        cy = -cx - cz
        return cx, cy, cz
    cx1, cy1, cz1 = offset_to_cube(x1, y1)
    cx2, cy2, cz2 = offset_to_cube(x2, y2)
    return (abs(cx1 - cx2) + abs(cy1 - cy2) + abs(cz1 - cz2)) // 2


def get_tiles_in_range(x: int, y: int, radius: int):
    """Get all tiles within radius (excluding center)."""
    tiles = []
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            if (nx, ny) != (x, y) and hex_distance(x, y, nx, ny) <= radius:
                tiles.append((nx, ny))
    return tiles


# =============================================================================
# Map Parsing
# =============================================================================

def parse_map_dump(dump_path):
    """Parse the SQLite dump file into structured data."""
    with open(dump_path, 'r') as f:
        content = f.read()

    # Parse map metadata
    m = re.search(r"INSERT INTO Map VALUES\('Default',(\d+),(\d+)", content)
    width = int(m.group(1))
    height = int(m.group(2))

    # Parse plots
    plots = {}
    plot_pattern = r"INSERT INTO Plots VALUES\((\d+),'([^']+)','([^']*)',(\d)\)"
    for m in re.finditer(plot_pattern, content):
        plot_id = int(m.group(1))
        terrain = m.group(2)
        continent = m.group(3)
        is_impassable = bool(int(m.group(4)))
        x = plot_id % width
        y = plot_id // width
        plots[(x, y)] = {
            'id': plot_id,
            'terrain': terrain,
            'continent': continent,
            'is_impassable': is_impassable,
            'x': x,
            'y': y,
            'rivers': set(),
            'feature': None,
            'resource': None,
        }

    # Parse plot rivers
    river_pattern = r"INSERT INTO PlotRivers VALUES\((\d+),(\d+),(\d+),(\d+),(-?\d+),(-?\d+),(-?\d+)\)"
    for m in re.finditer(river_pattern, content):
        plot_id = int(m.group(1))
        is_ne = bool(int(m.group(2)))
        is_w = bool(int(m.group(3)))
        is_nw = bool(int(m.group(4)))
        x = plot_id % width
        y = plot_id // width
        if (x, y) in plots:
            rivers = set()
            if is_ne:
                rivers.add('NE')
            if is_w:
                rivers.add('W')
            if is_nw:
                rivers.add('NW')
            plots[(x, y)]['rivers'] = rivers

    # Parse plot features (table is corrupted but let's try)
    feature_pattern = r"INSERT INTO PlotFeatures VALUES\((\d+),'([^']+)'\)"
    for m in re.finditer(feature_pattern, content):
        plot_id = int(m.group(1))
        feature = m.group(2)
        x = plot_id % width
        y = plot_id // width
        if (x, y) in plots:
            plots[(x, y)]['feature'] = feature

    # Parse plot resources
    resource_pattern = r"INSERT INTO PlotResources VALUES\((\d+),'([^']+)',(\d+)\)"
    for m in re.finditer(resource_pattern, content):
        plot_id = int(m.group(1))
        resource = m.group(2)
        count = int(m.group(3))
        x = plot_id % width
        y = plot_id // width
        if (x, y) in plots:
            plots[(x, y)]['resource'] = resource
            plots[(x, y)]['resource_count'] = count

    # Parse routes
    route_pattern = r"INSERT INTO PlotRoutes VALUES\((\d+),'([^']+)','([^']*)',(\d+)\)"
    for m in re.finditer(route_pattern, content):
        plot_id = int(m.group(1))
        x = plot_id % width
        y = plot_id // width
        if (x, y) in plots:
            plots[(x, y)]['route'] = m.group(2)

    return width, height, plots


# =============================================================================
# Tile Classification
# =============================================================================

def is_land(tile):
    terrain = tile['terrain']
    return terrain not in ('TERRAIN_OCEAN', 'TERRAIN_COAST', 'TERRAIN_LAKE',
                            'TERRAIN_GRASS_MOUNTAIN')


def can_place_city(tile):
    return is_land(tile)


def can_place_district(tile, district_type):
    terrain = tile['terrain']

    if terrain == 'TERRAIN_GRASS_MOUNTAIN':
        return False
    if terrain == 'TERRAIN_OCEAN':
        return False

    if terrain == 'TERRAIN_COAST':
        return district_type in ('HARBOR', 'WATER_PARK')

    if district_type in ('HARBOR', 'WATER_PARK'):
        return False

    return is_land(tile)


def is_on_river(tile):
    return len(tile.get('rivers', set())) > 0


# =============================================================================
# Adjacency Calculation
# =============================================================================

def compute_adjacency(district_type, x, y, plots, placements, city_center):
    """Compute adjacency bonus for a district at given position."""
    neighbors = get_neighbors(x, y)

    if district_type == 'CAMPUS':
        return _compute_campus(neighbors, plots, placements, city_center)
    elif district_type == 'HOLY_SITE':
        return _compute_holy_site(neighbors, plots, placements, city_center)
    elif district_type == 'THEATER_SQUARE':
        return _compute_theater_square(neighbors, plots, placements, city_center)
    elif district_type == 'COMMERCIAL_HUB':
        return _compute_commercial_hub(neighbors, plots, placements, city_center, x, y)
    elif district_type == 'HARBOR':
        return _compute_harbor(neighbors, plots, placements, city_center)
    elif district_type == 'INDUSTRIAL_ZONE':
        return _compute_industrial_zone(neighbors, plots, placements, city_center)
    else:
        return 0.0


def _count_adjacent_gp(neighbors, placements):
    """Count Government Plaza adjacency bonus."""
    count = 0
    for nx, ny in neighbors:
        if (nx, ny) in placements and placements[(nx, ny)] == 'GOVERNMENT_PLAZA':
            count += 1
    return count * 1.0


def _count_adjacent_districts(neighbors, placements, city_center, exclude_self=None):
    """Count +0.5 per district adjacency (floored per 2 districts)."""
    count = 0
    for nx, ny in neighbors:
        if (nx, ny) == city_center:
            count += 1
        elif (nx, ny) in placements:
            count += 1
    return math.floor(count / 2.0) * 0.5


def _compute_campus(neighbors, plots, placements, city_center):
    bonus = 0.0
    mountain_count = 0
    rainforest_count = 0

    for nx, ny in neighbors:
        tile = plots.get((nx, ny))
        if tile is None:
            continue
        if tile['terrain'] == 'TERRAIN_GRASS_MOUNTAIN':
            mountain_count += 1
        if tile.get('feature') == 'FEATURE_JUNGLE':
            rainforest_count += 1

    bonus += mountain_count * 1.0
    bonus += math.floor(rainforest_count / 2.0) * 0.5
    bonus += _count_adjacent_districts(neighbors, placements, city_center)
    bonus += _count_adjacent_gp(neighbors, placements)
    return bonus


def _compute_holy_site(neighbors, plots, placements, city_center):
    bonus = 0.0
    mountain_count = 0
    woods_count = 0

    for nx, ny in neighbors:
        tile = plots.get((nx, ny))
        if tile is None:
            continue
        if tile['terrain'] == 'TERRAIN_GRASS_MOUNTAIN':
            mountain_count += 1
        if tile.get('feature') == 'FEATURE_FOREST':
            woods_count += 1

    bonus += mountain_count * 1.0
    bonus += math.floor(woods_count / 2.0) * 0.5
    bonus += _count_adjacent_districts(neighbors, placements, city_center)
    bonus += _count_adjacent_gp(neighbors, placements)
    return bonus


def _compute_theater_square(neighbors, plots, placements, city_center):
    bonus = 0.0
    ec_wp_count = 0

    for nx, ny in neighbors:
        if (nx, ny) in placements:
            dt = placements[(nx, ny)]
            if dt in ('ENTERTAINMENT_COMPLEX', 'WATER_PARK'):
                ec_wp_count += 1

    bonus += ec_wp_count * 2.0
    bonus += _count_adjacent_districts(neighbors, placements, city_center)
    bonus += _count_adjacent_gp(neighbors, placements)
    return bonus


def _compute_commercial_hub(neighbors, plots, placements, city_center, x, y):
    bonus = 0.0
    tile = plots.get((x, y))

    if tile and is_on_river(tile):
        bonus += 2.0

    harbor_count = 0
    for nx, ny in neighbors:
        if (nx, ny) in placements and placements[(nx, ny)] == 'HARBOR':
            harbor_count += 1

    bonus += harbor_count * 2.0
    bonus += _count_adjacent_districts(neighbors, placements, city_center)
    bonus += _count_adjacent_gp(neighbors, placements)
    return bonus


def _compute_harbor(neighbors, plots, placements, city_center):
    bonus = 0.0
    cc_count = 0

    for nx, ny in neighbors:
        if (nx, ny) == city_center:
            cc_count += 1

    bonus += cc_count * 2.0
    bonus += _count_adjacent_districts(neighbors, placements, city_center)
    bonus += _count_adjacent_gp(neighbors, placements)
    return bonus


def _compute_industrial_zone(neighbors, plots, placements, city_center):
    bonus = 0.0
    adc_count = 0

    for nx, ny in neighbors:
        if (nx, ny) in placements:
            dt = placements[(nx, ny)]
            if dt in ('AQUEDUCT', 'DAM', 'CANAL'):
                adc_count += 1

    bonus += adc_count * 2.0
    bonus += _count_adjacent_districts(neighbors, placements, city_center)
    bonus += _count_adjacent_gp(neighbors, placements)
    return bonus


# =============================================================================
# Comprehensive Solver
# =============================================================================

def solve_scenario(scenario_path, map_base_path):
    with open(scenario_path, 'r') as f:
        scenario = json.load(f)

    map_file = scenario['map_file']
    map_path = map_base_path + map_file
    population = scenario['population']

    import subprocess, tempfile, os
    dump_path = tempfile.mktemp(suffix='.sql')
    try:
        subprocess.run(['sqlite3', map_path, '.dump'], stdout=open(dump_path, 'w'),
                      check=True, stderr=subprocess.DEVNULL)
        width, height, plots = parse_map_dump(dump_path)
    finally:
        if os.path.exists(dump_path):
            os.remove(dump_path)

    max_districts = 1 + math.floor((population - 1) / 3)

    # Find all city center candidates
    cc_candidates = []
    for y in range(height):
        for x in range(width):
            tile = plots.get((x, y))
            if tile and can_place_city(tile):
                cc_candidates.append((x, y))

    # All specialty district types that can give adjacency
    specialty_types = [
        'CAMPUS', 'HOLY_SITE', 'THEATER_SQUARE',
        'COMMERCIAL_HUB', 'HARBOR', 'INDUSTRIAL_ZONE',
        'GOVERNMENT_PLAZA'
    ]

    best_solution = None
    best_total = -1

    # For each city center, try all combinations of up to max_districts districts
    for cc_x, cc_y in cc_candidates:
        city_center = (cc_x, cc_y)

        # Get all valid district positions for this city
        district_candidates = {}
        for dt in specialty_types:
            tiles = []
            for y in range(height):
                for x in range(width):
                    if (x, y) == city_center:
                        continue
                    tile = plots.get((x, y))
                    if tile and can_place_district(tile, dt):
                        if hex_distance(cc_x, cc_y, x, y) <= 3:
                            tiles.append((x, y))
            district_candidates[dt] = tiles

        # Generate all valid placements of size up to max_districts
        # Use a more efficient approach: try all combinations
        all_valid_positions = {}
        for dt in specialty_types:
            all_valid_positions[dt] = district_candidates[dt]

        # Build a combined list of (dt, pos)
        options = []
        for dt in specialty_types:
            for pos in district_candidates[dt]:
                options.append((dt, pos))

        # Group by position to avoid conflicts
        # For each position, what districts can go there?
        pos_to_dts = defaultdict(list)
        for dt, pos in options:
            pos_to_dts[pos].append(dt)

        unique_positions = list(pos_to_dts.keys())

        # Try greedy with different first placements
        top_types = ['COMMERCIAL_HUB', 'CAMPUS', 'HOLY_SITE', 'INDUSTRIAL_ZONE',
                     'THEATER_SQUARE', 'GOVERNMENT_PLAZA']

        solution = find_best_greedy(plots, city_center, max_districts,
                                    unique_positions, pos_to_dts, top_types)

        if solution['total_adjacency'] > best_total:
            best_total = solution['total_adjacency']
            best_solution = solution

    # Format output for single city
    return {
        'city_center': best_solution['city_center'],
        'placements': best_solution['placements'],
        'adjacency_bonuses': best_solution['adjacency_bonuses'],
        'total_adjacency': best_solution['total_adjacency']
    }


def find_best_greedy(plots, city_center, max_districts, unique_positions, pos_to_dts, priority_order):
    """Find the best placement using a smarter greedy approach."""
    best_solution = None
    best_total = -1

    # Try placing first district at each promising position
    # First, filter to high-potential positions
    scored_positions = []
    for pos in unique_positions:
        px, py = pos
        available_dts = pos_to_dts[pos]
        best_dt_score = -1
        best_dt = None
        for dt in available_dts:
            if dt in ('GOVERNMENT_PLAZA',) and max_districts < 2:
                continue
            score = compute_adjacency(dt, px, py, plots, {}, city_center)
            if score > best_dt_score:
                best_dt_score = score
                best_dt = dt
        if best_dt and best_dt_score >= 0:
            scored_positions.append((pos, best_dt, best_dt_score))

    scored_positions.sort(key=lambda x: -x[2])

    # Try top 20 starting positions
    for start_pos, start_dt, start_score in scored_positions[:30]:
        placements = {}
        placements[start_pos] = start_dt

        # Greedily add remaining districts
        for _ in range(max_districts - 1):
            best_pos = None
            best_dt = None
            best_gain = -1

            for pos in unique_positions:
                if pos in placements:
                    continue
                px, py = pos
                for dt in pos_to_dts[pos]:
                    if dt in placements.values():
                        continue
                    if dt == 'GOVERNMENT_PLAZA' and 'GOVERNMENT_PLAZA' in placements.values():
                        continue

                    # Compute total adjacency with this addition
                    test_placements = dict(placements)
                    test_placements[pos] = dt
                    total = compute_total_adjacency(plots, city_center, test_placements)

                    old_total = compute_total_adjacency(plots, city_center, placements)
                    gain = total - old_total

                    if gain > best_gain:
                        best_gain = gain
                        best_pos = pos
                        best_dt = dt

            if best_pos is None:
                break
            placements[best_pos] = best_dt

        total = compute_total_adjacency(plots, city_center, placements)
        if total > best_total:
            best_total = total
            adjacency_bonuses = compute_all_adjacency(plots, city_center, placements)
            best_solution = {
                'city_center': list(city_center),
                'placements': {dt: list(pos) for pos, dt in placements.items()},
                'adjacency_bonuses': {dt: adj for dt, adj in adjacency_bonuses.items()
                                     if dt in placements.values()},
                'total_adjacency': total
            }

    if best_solution is None:
        # Fallback: just pick any valid placements
        placements = {}
        for pos in unique_positions:
            if len(placements) >= max_districts:
                break
            for dt in pos_to_dts[pos]:
                if dt not in placements.values():
                    placements[pos] = dt
                    break

        total = compute_total_adjacency(plots, city_center, placements)
        adjacency_bonuses = compute_all_adjacency(plots, city_center, placements)
        best_solution = {
            'city_center': list(city_center),
            'placements': {dt: list(pos) for pos, dt in placements.items()},
            'adjacency_bonuses': {dt: adj for dt, adj in adjacency_bonuses.items()
                                 if dt in placements.values()},
            'total_adjacency': total
        }

    return best_solution


def compute_total_adjacency(plots, city_center, placements):
    """Compute total adjacency bonus for all placed districts."""
    total = 0.0
    for (px, py), dt in placements.items():
        total += compute_adjacency(dt, px, py, plots, placements, city_center)
    return total


def compute_all_adjacency(plots, city_center, placements):
    """Compute adjacency for each district."""
    result = {}
    for (px, py), dt in placements.items():
        result[dt] = compute_adjacency(dt, px, py, plots, placements, city_center)
    return result
