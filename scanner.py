# =====================================================================
# PROYECTO: Detector de Archivos Duplicados
# AUTORS: [Dilan A. González Alatriste / Equipo de Desarrollo]
# MATERIA: Estructuras de Datos y sus Aplicaciones
# DESCRIPCIÓN: Interfaz gráfica moderna (CustomTkinter) de alto rendimiento.
#              Permite seleccionar carpetas, configurar filtros, ver
#              progreso en tiempo real, exportar CSV y eliminar duplicados.
# =====================================================================

import os
import ctypes
import hashlib
from typing import Dict, List, Set, Tuple, Callable, Optional, Any

# =====================================================================
# ETAPA 2: ALGORITMO HASH PARCIAL MANUAL (FNV-1a 64-bit)
# Justificación: FNV-1a es extremadamente rápido y tiene excelente
# distribución. Implementado manualmente sin bibliotecas.
# =====================================================================
def fnv1a_64(data: bytes) -> int:
    """
    Calcula el hash FNV-1a de 64 bits para una secuencia de bytes.
    """
    h = 0xcbf29ce484222325
    prime = 0x100000001b3
    for byte in data:
        h ^= byte
        h = (h * prime) & 0xffffffffffffffff
    return h


def get_partial_hash(filepath: str, size: int) -> int:
    """
    Lee bloques selectivos del archivo (inicio, medio, fin) de 4KB cada uno
    y calcula el hash FNV-1a de su concatenación. Si el archivo es menor o
    igual a 12 KB, calcula el hash de todo el contenido.
    """
    if size <= 12288:  # 12 KB
        with open(filepath, 'rb') as f:
            data = f.read()
        return fnv1a_64(data)

    # Si es mayor a 12KB, muestreamos inicio, medio y fin
    with open(filepath, 'rb') as f:
        # Inicio (primeros 4KB)
        start_data = f.read(4096)

        # Medio (4KB en el centro)
        f.seek((size // 2) - 2048)
        middle_data = f.read(4096)

        # Fin (últimos 4KB)
        f.seek(size - 4096)
        end_data = f.read(4096)

    combined = start_data + middle_data + end_data
    return fnv1a_64(combined)


# =====================================================================
# ETAPA 3: HASH COMPLETO (SHA-256 de biblioteca estándar)
# Justificación: Alta seguridad y resistencia a colisiones, crucial
# para justificar la eliminación de archivos duplicados de forma segura.
# Lectura en bloques de 64 KB para manejar archivos de >10MB eficientemente.
# =====================================================================
def get_full_hash(filepath: str) -> str:
    """
    Calcula el hash SHA-256 completo leyendo el archivo por bloques.
    """
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(65536)  # Bloques de 64 KB
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def is_hidden_or_system(filepath: str) -> bool:
    """
    Determina si un archivo es oculto o de sistema en Windows.
    También descarta archivos con nombres reservados del sistema.
    """
    basename = os.path.basename(filepath)
    basename_lower = basename.lower()
    
    # 1. Filtros por nombre común de sistema
    if basename_lower in ['desktop.ini', 'thumbs.db', '.ds_store', 'ntuser.dat', 'index.dat']:
        return True
    if basename_lower.startswith('~$'):  # Archivos temporales de Office
        return True

    # 2. Atributos de sistema de Windows
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
        if attrs != -1:
            # FILE_ATTRIBUTE_HIDDEN = 0x2, FILE_ATTRIBUTE_SYSTEM = 0x4
            if attrs & (0x2 | 0x4):
                return True
    except Exception:
        # Si falla en sistemas sin ctypes o por permisos, continuamos
        pass
        
    return False


class DuplicateScanner:
    def __init__(self):
        self.cancelled = False
        self.errors: List[str] = []

    def cancel(self):
        """Cancela el escaneo en ejecución."""
        self.cancelled = True

    def scan(self, 
             directories: List[str], 
             extensions: Set[str], 
             progress_callback: Callable[[str, int, int, str], None]) -> Dict[str, List[Tuple[str, int]]]:
        """
        Ejecuta el escaneo de directorios aplicando el proceso de deduplicación de 3 etapas.
        Retorna los duplicados agrupados por hash completo:
        { full_hash: [(filepath, size), ...] }
        """
        self.cancelled = False
        self.errors = []
        
        # Normalizar extensiones (pasar a minúsculas y asegurar que tengan punto)
        norm_extensions = set()
        for ext in extensions:
            ext = ext.strip().lower()
            if ext:
                if not ext.startswith('.'):
                    ext = '.' + ext
                norm_extensions.add(ext)

        # -------------------------------------------------------------
        # ETAPA 1: Búsqueda y agrupación por tamaño de archivo
        # -------------------------------------------------------------
        progress_callback('scanning', 0, 0, "Explorando directorios...")
        
        size_groups: Dict[int, List[str]] = {}
        total_files_discovered = 0
        
        for root_dir in directories:
            if self.cancelled:
                return {}
            
            if not os.path.isdir(root_dir):
                self.errors.append(f"Directorio no válido: {root_dir}")
                continue
                
            for root, dirs, files in os.walk(root_dir):
                # Filtrar directorios del sistema para evitar entrar en ellos
                dirs[:] = [d for d in dirs if d.lower() not in [
                    '$recycle.bin', 'system volume information', '.git', '.idea', '.vscode'
                ]]
                
                for filename in files:
                    if self.cancelled:
                        return {}
                        
                    filepath = os.path.join(root, filename)
                    
                    # Filtro de archivos del sistema u ocultos
                    if is_hidden_or_system(filepath):
                        continue
                        
                    # Filtro de extensiones
                    if norm_extensions:
                        _, ext = os.path.splitext(filename.lower())
                        if ext not in norm_extensions:
                            continue
                            
                    try:
                        size = os.path.getsize(filepath)
                        if size not in size_groups:
                            size_groups[size] = []
                        size_groups[size].append(filepath)
                        total_files_discovered += 1
                        
                        # Actualizar interfaz ocasionalmente
                        if total_files_discovered % 50 == 0:
                            progress_callback('scanning', total_files_discovered, 0, 
                                              f"Archivos descubiertos: {total_files_discovered}")
                    except Exception as e:
                        self.errors.append(f"Error al obtener tamaño de {filepath}: {str(e)}")
                        
        if self.cancelled:
            return {}

        # Filtrar grupos de tamaño: quedarnos solo con tamaños que tienen más de 1 archivo
        candidate_sizes = {sz: paths for sz, paths in size_groups.items() if len(paths) > 1}
        total_candidates_stage1 = sum(len(paths) for paths in candidate_sizes.values())
        
        progress_callback('scanning_done', total_candidates_stage1, total_files_discovered, 
                          f"Etapa 1 finalizada. Candidatos: {total_candidates_stage1} de {total_files_discovered} archivos.")

        if not candidate_sizes:
            return {}

        # -------------------------------------------------------------
        # ETAPA 2: Hash rápido/parcial en grupos de tamaño redundantes
        # -------------------------------------------------------------
        progress_callback('partial_hashing', 0, total_candidates_stage1, "Iniciando hash parcial (FNV-1a)...")
        
        partial_groups: Dict[Tuple[int, int], List[str]] = {}
        processed_candidates = 0
        
        for size, paths in candidate_sizes.items():
            for filepath in paths:
                if self.cancelled:
                    return {}
                
                try:
                    p_hash = get_partial_hash(filepath, size)
                    key = (size, p_hash)
                    if key not in partial_groups:
                        partial_groups[key] = []
                    partial_groups[key].append(filepath)
                except Exception as e:
                    self.errors.append(f"Error en hash parcial de {filepath}: {str(e)}")
                    
                processed_candidates += 1
                if processed_candidates % 10 == 0 or processed_candidates == total_candidates_stage1:
                    progress_callback('partial_hashing', processed_candidates, total_candidates_stage1,
                                      f"Calculando hash parcial: {processed_candidates}/{total_candidates_stage1}")

        # Filtrar grupos de hash parcial: quedarnos solo con grupos que tienen más de 1 archivo
        candidate_partials = {key: paths for key, paths in partial_groups.items() if len(paths) > 1}
        total_candidates_stage2 = sum(len(paths) for paths in candidate_partials.values())

        if self.cancelled:
            return {}

        progress_callback('partial_done', total_candidates_stage2, total_candidates_stage1,
                          f"Etapa 2 finalizada. Candidatos filtrados: {total_candidates_stage2}.")

        if not candidate_partials:
            return {}

        # -------------------------------------------------------------
        # ETAPA 3: Hash completo en candidatos finales (SHA-256)
        # -------------------------------------------------------------
        progress_callback('full_hashing', 0, total_candidates_stage2, "Iniciando hash completo (SHA-256)...")
        
        full_groups: Dict[str, List[Tuple[str, int]]] = {}
        processed_finals = 0
        
        for (size, _), paths in candidate_partials.items():
            for filepath in paths:
                if self.cancelled:
                    return {}
                
                try:
                    f_hash = get_full_hash(filepath)
                    if f_hash not in full_groups:
                        full_groups[f_hash] = []
                    # Guardamos la tupla (ruta, tamaño)
                    full_groups[f_hash].append((filepath, size))
                except Exception as e:
                    self.errors.append(f"Error en hash completo de {filepath}: {str(e)}")
                    
                processed_finals += 1
                if processed_finals % 5 == 0 or processed_finals == total_candidates_stage2:
                    progress_callback('full_hashing', processed_finals, total_candidates_stage2,
                                      f"Calculando hash completo: {processed_finals}/{total_candidates_stage2}")

        # Filtrar grupos finales de duplicados reales
        duplicates = {hash_val: items for hash_val, items in full_groups.items() if len(items) > 1}
        
        progress_callback('completed', len(duplicates), total_files_discovered, 
                          f"Escaneo completado. Se encontraron {len(duplicates)} grupos de duplicados.")
                          
        return duplicates
