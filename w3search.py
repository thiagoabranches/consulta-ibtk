#!/usr/bin/env python3
"""w3search - busca rapida de habilidades (w3a), unidades (w3u) e itens (w3t)
dentro de um mapa Warcraft 3 (.w3x), sem abrir o World Editor.

Exemplos:
    python w3search.py -n "lightning" --type ability
    python w3search.py -i "HolyBolt" -m testes_ultimato/TH_v143.w3x
    python w3search.py -b AHtb
    python w3search.py -id B310
"""
import argparse
import os
import sys
from dataclasses import dataclass

# Encoding: Git Bash/Windows costuma usar cp1252 e quebra com acentos.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_MAP = "testes_ultimato/TH_v142.w3x"

# tipo -> (arquivo dentro do MPQ, campo nome, campo icone, campo hotkey)
TYPES = {
    "ability": ("war3map.w3a", "anam", "aart", "ahky"),
    "unit":    ("war3map.w3u", "unam", "uico", "uhot"),
    "item":    ("war3map.w3t", "unam", "iico", "uhot"),
}
TYPE_LABEL = {"ability": "ABILITY", "unit": "UNIT", "item": "ITEM"}
EMPTY = "N/A"


class W3Error(Exception):
    """Erro amigavel, mostrado sem traceback."""


@dataclass
class W3Object:
    type: str
    id: str
    name: str = EMPTY
    base: str = EMPTY
    icon: str = EMPTY
    hotkey: str = EMPTY
    custom: bool = False


# --------------------------------------------------------------------------
# Adaptador para decrypt_mpq / wc3obj
# Se a API real for diferente, ajuste APENAS esta secao.
# --------------------------------------------------------------------------
def _import(name):
    try:
        return __import__(name)
    except ImportError as e:
        raise W3Error(f"Nao foi possivel importar a biblioteca local '{name}': {e}\n"
                      f"Rode o script na pasta onde {name}.py esta.")


def _read_from_mpq(mpq_mod, map_path, inner_name):
    """Devolve os bytes de `inner_name` dentro do .w3x (ou None se nao existir)."""
    try:
        data = mpq_mod.ler_arquivo(map_path, inner_name)
    except (KeyError, FileNotFoundError):
        return None
    if data is not None and not isinstance(data, (bytes, bytearray)) and hasattr(data, "read"):
        data = data.read()
    return data or None


def _parse_objects(obj_mod, kind, data):
    """Devolve {'original': {...}, 'custom': {...}} a partir dos bytes do arquivo."""
    ext = TYPES[kind][0].rsplit(".", 1)[1]  # w3a / w3u / w3t
    try:
        return obj_mod.parse_object_file(data, ext)
    except (ValueError, KeyError):
        return obj_mod.parse_object_file(data, TYPES[kind][0])  # tenta 'war3map.w3a'


# --------------------------------------------------------------------------
# Extracao de campos
# --------------------------------------------------------------------------
def _text(v):
    """Normaliza um valor (bytes, lista por nivel, vazio) para str."""
    if isinstance(v, (list, tuple)):
        v = next((x for x in v if x not in (None, "", b"")), None)
    if isinstance(v, dict) and "value" in v:
        v = v["value"]
    if isinstance(v, (bytes, bytearray)):
        v = v.decode("utf-8", errors="replace")
    v = "" if v is None else str(v).strip().strip("\x00")
    return v or EMPTY


def _get_mod(mods, code):
    """`mods` pode ser dict {'anam': v} ou lista de {'id': 'anam', 'value': v} / tuplas."""
    if not mods:
        return EMPTY
    if isinstance(mods, dict):
        return _text(mods.get(code))
    for m in mods:
        if isinstance(m, dict):
            if code in (m.get("id"), m.get("field"), m.get("code")):
                return _text(m.get("value"))
        elif isinstance(m, (list, tuple)) and len(m) >= 2 and m[0] == code:
            return _text(m[1])
    return EMPTY


def _split_key(key, entry, is_custom):
    """Resolve (id, base) de uma entrada; chaves custom podem vir como 'B310:AHtb'."""
    key = _text(key)
    base = _text(entry.get("base") or entry.get("base_id") or entry.get("old_id")) \
        if isinstance(entry, dict) else EMPTY
    if ":" in key:
        a, b = key.split(":", 1)
        key, base = (a, b) if base == EMPTY else (a, base)
    if not is_custom:
        base = key
    return key, base


def load_data(map_path, kinds):
    """Le o mapa e devolve lista de W3Object dos tipos pedidos."""
    if not os.path.isfile(map_path):
        raise W3Error(f"Mapa nao encontrado: {map_path}")
    mpq_mod, obj_mod = _import("decrypt_mpq"), _import("wc3obj")

    objects = []
    for kind in kinds:
        inner, f_name, f_icon, f_hot = TYPES[kind]
        try:
            data = _read_from_mpq(mpq_mod, map_path, inner)
            if data is None:
                continue  # mapa sem esse tipo de objeto: normal
            parsed = _parse_objects(obj_mod, kind, data)
        except W3Error:
            raise
        except Exception as e:
            raise W3Error(f"Falha ao ler {inner} de '{map_path}': {type(e).__name__}: {e}")

        for section in ("original", "custom"):
            is_custom = section == "custom"
            for key, entry in ((parsed or {}).get(section) or {}).items():
                mods = entry.get("mods") if isinstance(entry, dict) else entry
                oid, base = _split_key(key, entry, is_custom)
                objects.append(W3Object(kind, oid, _get_mod(mods, f_name), base,
                                        _get_mod(mods, f_icon), _get_mod(mods, f_hot), is_custom))
    return objects


# --------------------------------------------------------------------------
# Busca e saida
# --------------------------------------------------------------------------
def search_objects(objects, name=None, icon=None, base=None, oid=None):
    """Filtros combinados com AND. Nome/icone: substring case-insensitive; base/id: exato."""
    out = []
    for o in objects:
        if name and name.lower() not in o.name.lower():
            continue
        if icon and icon.lower() not in o.icon.lower():
            continue
        if base and o.base != base:
            continue
        if oid and o.id != oid:
            continue
        out.append(o)
    return sorted(out, key=lambda o: (o.type, o.id))


def print_results(results):
    headers = ["TYPE", "ID", "NAME", "BASE", "ICON", "HOTKEY"]
    rows = [[TYPE_LABEL[o.type], o.id, o.name, o.base, o.icon, o.hotkey] for o in results]
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    line = "-+-".join("-" * w for w in widths)
    fmt = lambda r: " | ".join(f"{str(c):<{w}}" for c, w in zip(r, widths)).rstrip()
    print(fmt(headers))
    print(line)
    for r in rows:
        print(fmt(r))
    print(f"\n{len(rows)} resultado(s).")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Busca habilidades, unidades e itens em mapas .w3x")
    p.add_argument("-m", "--map", default=DEFAULT_MAP, help=f"arquivo .w3x (default: {DEFAULT_MAP})")
    p.add_argument("-n", "--name", help="busca parcial no nome (anam/unam)")
    p.add_argument("-i", "--icon", help="busca parcial no icone (aart/uico/iico)")
    p.add_argument("-b", "--base", help="ID base exato (ex: AHtb)")
    p.add_argument("-id", dest="id", help="ID customizado exato (ex: B310)")
    p.add_argument("--type", choices=list(TYPES), help="ability, unit ou item (default: todos)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not any([args.name, args.icon, args.base, args.id]):
        print("Aviso: sem filtros, listando todos os objetos.", file=sys.stderr)
    try:
        objects = load_data(args.map, [args.type] if args.type else list(TYPES))
    except W3Error as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    results = search_objects(objects, args.name, args.icon, args.base, args.id)
    if not results:
        print("Nenhum resultado encontrado.")
        return 0
    print_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
