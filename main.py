from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pyodbc
import csv
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
import json

# Cargar variables de entorno desde .env
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicializar FastAPI
app = FastAPI(
    title="Inventario API",
    description="API para obtener datos de inventario desde SQL Server",
    version="1.0.0"
)

# Configurar CORS para Power Apps y otros clientes
cors_origins = os.getenv('CORS_ORIGINS', '["http://localhost:3000","https://apps.powerapps.com"]')
try:
    cors_list = json.loads(cors_origins)
except (json.JSONDecodeError, TypeError):
    cors_list = ['http://localhost:3000', 'https://apps.powerapps.com']

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_list,
    allow_credentials=True,
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)

logger.info(f"CORS configurado para orígenes: {cors_list}")

def get_connection():
    """Obtiene conexión a SQL Server usando variables de entorno."""
    try:
        db_server = os.getenv('DB_SERVER')
        db_database = os.getenv('DB_DATABASE')
        db_username = os.getenv('DB_USERNAME')
        db_password = os.getenv('DB_PASSWORD')
        db_driver = os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')

        if not all([db_server, db_database, db_username, db_password]):
            raise ValueError("Faltan variables de entorno de base de datos")

        connection_string = f"DRIVER={{{db_driver}}};SERVER={db_server};DATABASE={db_database};UID={db_username};PWD={db_password}"
        conn = pyodbc.connect(connection_string)
        logger.info("Conexión a SQL Server establecida")
        return conn
    except pyodbc.Error as e:
        logger.error(f"Error de conexión ODBC: {str(e)}")
        raise HTTPException(status_code=503, detail="No se pudo conectar a la base de datos")


@app.get("/obtenerinventario", tags=["Inventario"], summary="Obtener datos de inventario")
def obtener_inventario():
    """
    Obtiene datos de inventario desde SQL Server.
    Ejecuta un stored procedure y retorna los datos en formato JSON.
    También guarda un archivo CSV con los datos.
    """
    conn = None
    cursor = None
    
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Parámetros del stored procedure
        params = [
            '609',  # Param 1
            '0',    # Param 2
            '0',    # Param 3
            '0',    # Param 4
            '1',    # Param 5
            '11527', # Param 6
            '0',    # Param 7
            '0',    # Param 8
            '0',    # Param 9
            '0',    # Param 10
            '0',    # Param 11
            '0',    # Param 12
            '760'   # Param 13
        ]

        sql = """
            SET NOCOUNT ON;
            EXEC GetCotEstadis_250A_corepV4
            ?,?,?,?,?,?,?,?,?,?,?,?,?
        """

        logger.info("Ejecutando stored procedure GetCotEstadis_250A_corepV4")
        cursor.execute(sql, params)

        if cursor.description is None:
            logger.warning("El stored procedure no devolvió datos")
            return {
                "exito": False,
                "mensaje": "El stored procedure no devolvió datos",
                "timestamp": datetime.now().isoformat()
            }

        columnas = [c[0] for c in cursor.description]
        filas = cursor.fetchall()
        
        logger.info(f"Recuperados {len(filas)} registros")

        # Generar CSV (se sobreescribe)
        nombre_archivo = "inventario.csv"
        try:
            with open(nombre_archivo, mode="w", newline="", encoding="utf-8") as archivo:
                writer = csv.writer(archivo)
                writer.writerow(columnas)
                for fila in filas:
                    writer.writerow(fila)
            logger.info(f"CSV generado exitosamente: {nombre_archivo}")
        except IOError as e:
            logger.error(f"Error escribiendo CSV: {str(e)}")
            raise HTTPException(status_code=500, detail="Error escribiendo archivo CSV")

        # Convertir filas a lista de diccionarios para JSON
        resultado = [dict(zip(columnas, fila)) for fila in filas]

        response = {
            "exito": True,
            "archivo_actualizado": nombre_archivo,
            "total_registros": len(resultado),
            "timestamp": datetime.now().isoformat(),
            "datos": resultado
        }
        
        logger.info(f"Solicitud completada exitosamente. {len(resultado)} registros devueltos.")
        return response

    except HTTPException:
        raise
    except pyodbc.Error as e:
        logger.error(f"Error ODBC: {str(e)}")
        raise HTTPException(status_code=503, detail="Error en base de datos")
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logger.info("Conexión cerrada")


@app.get("/health", tags=["Salud"], summary="Verificar estado de la API")
def health_check():
    """Endpoint de health check para monitoreo."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/", tags=["Info"], summary="Información de la API")
def root():
    """Endpoint raíz con información de la API."""
    return {
        "nombre": "Inventario API",
        "version": "1.0.0",
        "endpoints": [
            {"ruta": "/obtenerinventario", "metodo": "GET", "descripcion": "Obtener datos de inventario"},
            {"ruta": "/health", "metodo": "GET", "descripcion": "Verificar estado de la API"},
            {"ruta": "/docs", "metodo": "GET", "descripcion": "Documentación API (Swagger)"}
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('API_PORT', 8000))
    host = os.getenv('API_HOST', '0.0.0.0')
    uvicorn.run(app, host=host, port=port)
