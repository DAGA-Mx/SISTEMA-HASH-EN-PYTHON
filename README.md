# Detector de Archivos Duplicados Inteligente

Un sistema de deduplicación de archivos de alto rendimiento diseñado en Python con una interfaz gráfica moderna utilizando **CustomTkinter**. El sistema implementa una arquitectura optimizada en 3 etapas de filtrado para minimizar el uso de I/O en disco, combinando hashing rápido por muestreo y hashing criptográfico completo.

---

## Integrantes del Equipo / Autor
* **Autor**:
* **Dilan Alejandro González Alatriste / Estudiante**
* **Materia**: Estructuras de Datos y sus Aplicaciones / Gestión de Almacenamiento


---

## Características Principales

* **Interfaz de Usuario Premium**: Interfaz fluida y responsiva con soporte nativo para Tema Oscuro/Claro.
* **Escaneo en 3 Etapas**:
  * **Etapa 1 (Tamaño)**: Agrupación instantánea por tamaño de archivo utilizando metadatos del sistema.
  * **Etapa 2 (Hash Parcial)**: Hashing manual FNV-1a sobre bloques muestreados (inicio, medio, fin).
  * **Etapa 3 (Hash Completo)**: Verificación SHA-256 por bloques de 64 KB para evitar colisiones.
* **Robusto contra fallos**: Diseñado para ignorar archivos del sistema de Windows y omitir de manera segura archivos sin permisos de lectura sin interrumpir el escaneo.
* **Mapeo de Espacio Potencial**: Visualización destacada en tiempo real de cuántos bytes y espacio en disco se pueden recuperar.
* **Acciones de Usuario**:
  * Selección inteligente de duplicados (marcar copias recomendadas manteniendo el original).
  * Apertura nativa de carpetas en Windows Explorer.
  * Eliminación permanente y segura directamente desde la aplicación.
  * Exportación de reportes detallados en formato CSV.

---

## Justificación Técnica de las Funciones Hash

El diseño del software implementa una combinación estratégica de dos funciones hash distintas:

### 1. Hash Parcial (Etapa 2): FNV-1a de 64 bits (Implementación Manual)
* **Algoritmo**: Fowler-Noll-Vo hash de 64 bits, variante FNV-1a.
* **Velocidad**: Extremadamente alta. Al implementarse de manera puramente aritmética (operaciones XOR y multiplicaciones de enteros de 64 bits sin bucles complejos o inicializaciones pesadas de memoria), tiene una sobrecarga de CPU prácticamente nula.
* **Estrategia de Muestreo (I/O)**: Para archivos de más de 12 KB, no lee todo el archivo. Lee 3 bloques estratégicos de 4 KB (inicio, centro y final del archivo). Esto es extremadamente eficiente para archivos grandes (ej. videos, imágenes de alta resolución, bases de datos), ya que evita leer megabytes de disco para archivos que tienen metadatos diferentes o firmas iniciales distintas.
* **Riesgo de Colisiones**: Aunque FNV-1a tiene un riesgo de colisiones bajo comparado con otros hashes aditivos elementales (gracias a su excelente distribución de bits), el riesgo aumenta al muestrear solo 12 KB del archivo. Por esta razón, el hash parcial **solo** se utiliza como un filtro rápido de descarte. Ningún archivo se elimina basándose únicamente en el hash parcial.

### 2. Hash Completo (Etapa 3): SHA-256 (Biblioteca Estándar)
* **Algoritmo**: Secure Hash Algorithm 2 (SHA-256).
* **Seguridad y Resistencia a Colisiones**: Virtualmente absoluta. SHA-256 es una función de hash criptográfica con una longitud de hash de 256 bits (lo que permite $2^{256}$ combinaciones posibles). La probabilidad de encontrar una colisión (dos archivos con contenidos distintos que produzcan el mismo hash) es de aproximadamente $1$ en $10^{77}$. Esto proporciona la seguridad necesaria de que, si dos archivos comparten el mismo hash completo, son **100% idénticos bit a bit**, evitando cualquier posible pérdida de datos accidental.
* **Velocidad**: Aunque SHA-256 es computacionalmente más costoso que FNV-1a, en Python se ejecuta sobre librerías en C altamente optimizadas (`hashlib`), aprovechando instrucciones por hardware del procesador (como las extensiones Intel SHA). Además, al aplicarse únicamente sobre los candidatos finalistas de la Etapa 2, el número de lecturas completas a disco es mínimo.

---

## Dependencias Necesarias

El proyecto está diseñado bajo Python 3.x y depende únicamente del paquete de interfaz gráfica moderna `customtkinter`.

Instalar dependencias ejecutando:
```bash
pip install -r requirements.txt
```

---

## Instrucciones de Uso

1. **Ejecutar la aplicación**:
   ```bash
   python main.py
   ```
2. **Seleccionar Carpetas**:
   * Haga clic en `+ Agregar` en el panel lateral para abrir el selector nativo y añadir una o más carpetas a la lista de análisis.
3. **Configurar Filtros**:
   * Por defecto, el sistema viene preconfigurado con filtros para extensiones `.txt` y `.jpg` (separadas por comas).
   * Puede desactivar la casilla `Habilitar Filtros` para analizar todos los archivos del directorio, o ingresar extensiones personalizadas (ej. `mp3, pdf, docx`).
4. **Iniciar Escaneo**:
   * Haga clic en `Iniciar Escaneo`. Verá el progreso visual, las etapas del algoritmo y los archivos leídos actualizarse en tiempo real.
5. **Gestionar Resultados**:
   * En el panel de resultados, los archivos duplicados se listarán en grupos ordenados de mayor a menor tamaño.
   * Utilice el botón `Marcar Copias` en la cabecera de cada grupo para seleccionar de manera automática todas las copias duplicadas de ese grupo, manteniendo el archivo original desmarcado para conservarlo.
   * Haga clic en el icono de la carpeta `📂` al lado de cualquier ruta para abrir directamente su ubicación en el Explorador de Windows y verificar el archivo manualmente.
6. **Eliminar y Liberar Espacio**:
   * Presione `Eliminar Seleccionados`. La aplicación le mostrará una ventana emergente de confirmación indicando exactamente cuántos archivos se borrarán y cuánto espacio se recuperará.
   * Al confirmar, se eliminarán los archivos y el panel de resultados se actualizará dinámicamente sin necesidad de volver a escanear.
7. **Exportar Reporte**:
   * Puede exportar la lista de duplicados a un reporte CSV detallado presionando `Exportar Reporte CSV`.

---

## Cómo generar el archivo ejecutable (.exe)

Para distribuir esta herramienta como una aplicación independiente para Windows que no requiera instalar Python ni librerías:

1. Instalar **PyInstaller**:
   ```bash
   pip install pyinstaller
   ```
2. Compilar el proyecto en un único archivo ejecutable:
   ```bash
   pyinstaller --noconsole --onefile --add-data "scanner.py;." main.py
   ```
   *Nota:* En sistemas Windows, asegúrese de separar con punto y coma (`;`).
3. El archivo ejecutable generado se encontrará en la carpeta recién creada llamada `dist/main.exe`.
