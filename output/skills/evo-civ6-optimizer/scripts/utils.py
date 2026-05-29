import sqlite3
import json
import math
import os
import tempfile
import subprocess
from itertools import combinations, permutations


def get_neighbors(x, y):
    if y % 2 == 0:
        directions = [(1,0), (0,-1), (-1,-1), (-1,0), (-1,1), (0,1)]
    else:
        directions = [(1,0), (1,-1), (0,-1), (-1,0), (0,1), (1,1)]
    return [(x + dx, y + dy) for dx, dy in directions]


def hex_distance(x1, y1, x2, y2):
    def offset_to_cube(col, row):
        cx = col - (row - (row & 1)) // 2
        cz = row
        cy = -cx - cz
        return cx, cy, cz
    cx1, cy1, cz1 = offset_to_cube(x1, y1)
    cx2, cy2, cz2 = offset_to_cube(x2, y2)
    return (abs(cx1-cx2) + abs(cy1-cy2) + abs(cz1-cz2)) // 2


def parse_civ6map(map_path):
    recovered_path = tempfile.mktemp(suffix='.sqlite')
    sql_path = tempfile.mktemp(suffix='.sql')
    try:
        result = subprocess.run(
            ['sqlite3', map_path, '.recover'],
            capture_output=True, text=True
        )
        with open(sql_path, 'w') as f:
            f.write(result.stdout)
        subprocess.run(['sqlite3', recovered_path], input=result.stdout, capture_output=True, text=True)
    except Exception:
        pass

    conn = sqlite3.connect(recovered_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM Map")
    map_info = dict(cursor.fetchone())
    width = map_info['Width']
    height = map_info['Height']

    cursor.execute("SELECT * FROM Plots")
    plots = {row['ID']: dict(row) for row in cursor.fetchall()}

    features = {}
    try:
        cursor.execute("SELECT * FROM PlotFeatures")
        features = {row['ID']: row['FeatureType'] for row in cursor.fetchall()}
    except Exception:
        pass

    resources = {}
    try:
        cursor.execute("SELECT * FROM PlotResources")
        resources = {row['ID']: row['ResourceType'] for row in cursor.fetchall()}
    except Exception:
        pass

    rivers = {}
    try:
        cursor.execute("SELECT * FROM PlotRivers")
        rivers = {row['ID']: dict(row) for row in cursor.fetchall()}
    except Exception:
        pass

    conn.close()
    os.unlink(recovered_path)
    os.unlink(sql_path)

    tiles = {}
    for plot_id, data in plots.items():
        x = plot_id % width
        y = plot_id // width
        terrain = data['TerrainType']
        tiles[(x, y)] = {
            'terrain': terrain,
            'feature': features.get(plot_id),
            'resource': resources.get(plot_id),
            'is_mountain': 'MOUNTAIN' in terrain,
            'is_water': terrain in ['TERRAIN_OCEAN', 'TERRAIN_COAST'],
            'is_hills': 'HILLS' in terrain,
            'has_river': plot_id in rivers,
        }

    return tiles, width, height


def calculate_adjacency(placements, city_center, tiles):
    pm = {coord: dtype for dtype, coord in placements.items()}
    pm[city_center] = 'CITY_CENTER'

    total = 0
    per_district = {}

    for dtype, coord in placements.items():
        if dtype in ['AQUEDUCT', 'NEIGHBORHOOD', 'CANAL', 'DAM', 'SPACEPORT',
                     'ENTERTAINMENT_COMPLEX', 'WATER_PARK', 'ENCAMPMENT', 'AERODROME',
                     'GOVERNMENT_PLAZA', 'PRESERVE']:
            continue

        x, y = coord
        nbrs = get_neighbors(x, y)
        bonus = 0

        if dtype in ['CAMPUS', 'HOLY_SITE']:
            mtns = sum(1 for nx, ny in nbrs if (nx, ny) in tiles and tiles[(nx, ny)]['is_mountain'])
            dists = sum(1 for nx, ny in nbrs if (nx, ny) in pm)
            bonus = mtns + math.floor(dists * 0.5)
        elif dtype == 'COMMERCIAL_HUB':
            rv = 2 if tiles[coord]['has_river'] else 0
            dists = sum(1 for nx, ny in nbrs if (nx, ny) in pm)
            bonus = rv + math.floor(dists * 0.5)
        elif dtype == 'INDUSTRIAL_ZONE':
            aqs = sum(1 for nx, ny in nbrs if (nx, ny) in pm and pm[(nx, ny)] in ['AQUEDUCT', 'DAM', 'CANAL'])
            dists = sum(1 for nx, ny in nbrs if (nx, ny) in pm)
            bonus = aqs * 2 + math.floor(dists * 0.5)
        elif dtype == 'THEATER_SQUARE':
            dists = sum(1 for nx, ny in nbrs if (nx, ny) in pm)
            bonus = math.floor(dists * 0.5)

        per_district[dtype] = bonus
        total += bonus

    return total, per_district


def optimize_scenario(scenario_path, output_path):
    with open(scenario_path) as f:
        scenario = json.load(f)

    map_dir = os.path.dirname(scenario_path)
    base_dir = os.path.dirname(map_dir)
    map_path = os.path.join(base_dir, scenario['map_file'])

    tiles, width, height = parse_civ6map(map_path)
    population = scenario['population']
    num_cities = scenario['num_cities']
    max_districts = 1 + (population - 1) // 3

    valid_tiles = [(x, y) for (x, y), t in tiles.items() if not t['is_water'] and not t['is_mountain']]

    best_total = 0
    best_solution = None

    for cc in valid_tiles:
        workable = [t for t in valid_tiles if t != cc and hex_distance(t[0], t[1], cc[0], cc[1]) <= 3]
        if len(workable) < max_districts:
            continue

        for spec_combo in combinations(['CAMPUS', 'COMMERCIAL_HUB', 'INDUSTRIAL_ZONE', 'HOLY_SITE', 'THEATER_SQUARE'], max_districts):
            dt_list = list(spec_combo)
            for tile_combo in permutations(workable, max_districts):
                placements = {dt_list[i]: tile_combo[i] for i in range(max_districts)}
                total, per_d = calculate_adjacency(placements, cc, tiles)
                if total > best_total:
                    best_total = total
                    best_solution = {
                        'city_center': list(cc),
                        'placements': {k: list(v) for k, v in placements.items()},
                        'adjacency_bonuses': per_d,
                        'total_adjacency': total
                    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(best_solution, f, indent=2)

    return best_solution
