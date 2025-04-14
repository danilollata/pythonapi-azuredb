from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import aiomysql
import os
from dotenv import load_dotenv
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI()
pool = None

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")


# Permitir solicitudes desde Live Server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Permitir todos los orígenes
    allow_credentials=False,      # Importante: debe ser False con "*" en allow_origins
    allow_methods=["*"],          # Permitir todos los métodos
    allow_headers=["*"],          # Permitir todos los headers
)

# MODELOS

class Repartidor(BaseModel):
    repartidor_id: int
    nombre: str
    apellido: str
    telefono: str

class EstadoEnvio(BaseModel):
    estado_id: int
    nombre_estado: str

class EnvioBase(BaseModel):
    remitente: str
    destinatario: str
    direccion_envio: str
    fecha_envio: datetime
    repartidor_id: int
    estado_id: int

class EnvioCreate(EnvioBase):
    pass

class EnvioOut(BaseModel):
    envio_id: int
    remitente: str
    destinatario: str
    direccion_envio: str
    fecha_envio: str
    nombre_repartidor: str
    apellido_repartidor: str
    estado: str

class Envio(EnvioBase):
    envio_id: int

# CONEXIÓN CON MYSQL

async def get_pool():
    global pool
    if pool is None:
        pool = await aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            autocommit=True
        )
    return pool

@app.on_event("startup")
async def startup():
    await get_pool()

@app.on_event("shutdown")
async def shutdown():
    if pool:
        pool.close()
        await pool.wait_closed()

# FUNCIÓN UTILITARIA PARA CONSULTAS

async def ejecutar_consulta(query, params=None):
    pool_obj = await get_pool()
    async with pool_obj.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(query, params)
            rows = await cursor.fetchall()
            return rows, cursor.description

# RUTA DE PRUEBA
@app.get("/")
async def root():
    return {"message": "Bienvenido papu"}

# COMBOS

@app.get("/api/v1/repartidores", response_model=list[Repartidor])
async def listar_repartidores():
    query = "CALL sp_cbox_listar_repartidor()"
    rows, description = await ejecutar_consulta(query)
    column_names = [col[0] for col in description]
    return [Repartidor(**dict(zip(column_names, row))) for row in rows]

@app.get("/api/v1/estados_envio", response_model=list[EstadoEnvio])
async def listar_estados_envio():
    query = "CALL sp_cbox_listar_estado_envio()"
    rows, description = await ejecutar_consulta(query)
    column_names = [col[0] for col in description]
    return [EstadoEnvio(**dict(zip(column_names, row))) for row in rows]

# ENVÍOS

@app.get("/api/v1/envios", response_model=list[EnvioOut])
async def listar_envios():
    query = "CALL sp_listar_envio()"
    rows, description = await ejecutar_consulta(query)
    column_names = [col[0] for col in description]

    envios = []
    for row in rows:
        envio_data = dict(zip(column_names, row))
        if isinstance(envio_data['fecha_envio'], datetime):
            envio_data['fecha_envio'] = envio_data['fecha_envio'].isoformat()
        envios.append(EnvioOut(**envio_data))
    return envios

@app.get("/api/v1/envio/{envio_id}", response_model=EnvioOut)
async def obtener_envio(envio_id: int):
    query = "CALL sp_listar_envio_por_id(%s)"
    params = (envio_id,)
    rows, description = await ejecutar_consulta(query, params)
    if not rows:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    column_names = [col[0] for col in description]
    envio_data = dict(zip(column_names, rows[0]))
    if isinstance(envio_data['fecha_envio'], datetime):
        envio_data['fecha_envio'] = envio_data['fecha_envio'].isoformat()
    return EnvioOut(**envio_data)

@app.post("/api/v1/envio", response_model=Envio)
async def crear_envio(envio: EnvioCreate):
    query = "CALL sp_crear_envio(%s, %s, %s, %s, %s, %s)"
    params = (
        envio.remitente,
        envio.destinatario,
        envio.direccion_envio,
        envio.fecha_envio,
        envio.repartidor_id,
        envio.estado_id
    )
    await ejecutar_consulta(query, params)

    rows, _ = await ejecutar_consulta("SELECT LAST_INSERT_ID()")
    last_id = rows[0][0]
    return Envio(envio_id=last_id, **envio.dict())

@app.put("/api/v1/envio/{envio_id}", response_model=Envio)
async def actualizar_envio(envio_id: int, envio: EnvioCreate):
    query = "CALL sp_actualizar_envio(%s, %s, %s, %s, %s, %s, %s)"
    params = (
        envio.remitente,
        envio.destinatario,
        envio.direccion_envio,
        envio.fecha_envio,
        envio.repartidor_id,
        envio.estado_id,
        envio_id
    )
    await ejecutar_consulta(query, params)
    return Envio(envio_id=envio_id, **envio.dict())

@app.delete("/api/v1/envio/{envio_id}")
async def eliminar_envio(envio_id: int):
    query = "CALL sp_eliminar_envio(%s)"
    await ejecutar_consulta(query, (envio_id,))
    return {"message": f"Envío con ID {envio_id} eliminado correctamente."}
