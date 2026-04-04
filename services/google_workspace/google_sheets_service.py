"""
Google Sheets Service - Manipulación automática de hojas de cálculo
Crea, edita, calcula y genera gráficos en Google Sheets automáticamente
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import json_log_formatter

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_SHEETS_LIBS_AVAILABLE = True
    GOOGLE_SHEETS_IMPORT_ERROR = None
except Exception as exc:
    build = None
    HttpError = Exception
    GOOGLE_SHEETS_LIBS_AVAILABLE = False
    GOOGLE_SHEETS_IMPORT_ERROR = exc

from services.google_workspace.google_auth_service import google_auth_service
from services.google_workspace.google_drive_service import google_drive_service

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("google_sheets_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(handler)
logger.propagate = False

class GoogleSheetsService:
    """
    Servicio completo de Google Sheets
    Creación, edición y análisis automático de hojas de cálculo
    """
    
    def __init__(self):
        self.sheet_templates = {
            "budget": {
                "title": "💰 Presupuesto",
                "headers": ["Categoría", "Presupuestado", "Real", "Diferencia", "% Variación"]
            },
            "sales_report": {
                "title": "📊 Reporte de Ventas",
                "headers": ["Producto", "Cantidad", "Precio Unitario", "Total", "Mes"]
            },
            "project_tracker": {
                "title": "🚀 Seguimiento de Proyecto",
                "headers": ["Tarea", "Responsable", "Estado", "Fecha Inicio", "Fecha Fin", "% Completado"]
            },
            "expense_report": {
                "title": "💳 Reporte de Gastos",
                "headers": ["Fecha", "Descripción", "Categoría", "Monto", "Método de Pago"]
            },
            "analytics_dashboard": {
                "title": "📈 Dashboard Analytics",
                "headers": ["Métrica", "Valor", "Objetivo", "Variación", "Tendencia"]
            }
        }

    async def _execute(self, request):
        return await asyncio.to_thread(request.execute)
    
    async def _get_sheets_service(self, user_email: str):
        """Obtiene el servicio de Google Sheets para un usuario."""
        if not GOOGLE_SHEETS_LIBS_AVAILABLE:
            raise RuntimeError(f"google_sheets_unavailable: {GOOGLE_SHEETS_IMPORT_ERROR}")
        credentials = await google_auth_service.get_valid_credentials(user_email)
        if not credentials:
            raise ValueError(f"No valid credentials for user: {user_email}")
        
        return await asyncio.to_thread(build, 'sheets', 'v4', credentials=credentials)
    
    async def create_spreadsheet(self, user_email: str, title: str,
                                template: Optional[str] = None,
                                folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Crea una nueva hoja de cálculo
        
        Args:
            user_email: Email del usuario
            title: Título de la hoja
            template: Template a usar (opcional)
            folder_id: ID de carpeta donde guardar (opcional)
            
        Returns:
            Dict con información de la hoja creada
        """
        try:
            service = await self._get_sheets_service(user_email)
            
            spreadsheet_body = {
                'properties': {
                    'title': title
                }
            }
            
            # Crear hoja
            spreadsheet = await self._execute(
                service.spreadsheets().create(
                    body=spreadsheet_body
                )
            )
            
            spreadsheet_id = spreadsheet['spreadsheetId']
            
            # Mover a carpeta específica si se especifica
            if folder_id:
                drive_service = await google_drive_service._get_drive_service(user_email)
                await google_drive_service._execute(
                    drive_service.files().update(
                        fileId=spreadsheet_id,
                        addParents=folder_id,
                        removeParents='root'
                    )
                )
            
            # Aplicar template si se especifica
            if template and template in self.sheet_templates:
                await self._apply_sheet_template(service, spreadsheet_id, template)
            
            logger.info({
                "event": "spreadsheet_created",
                "user_email": user_email,
                "title": title,
                "spreadsheet_id": spreadsheet_id,
                "template": template,
                "folder_id": folder_id
            })
            
            return {
                "spreadsheet_id": spreadsheet_id,
                "title": title,
                "web_view_link": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
                "created_time": datetime.utcnow().isoformat(),
                "template_applied": template is not None
            }
            
        except Exception as e:
            logger.error({
                "event": "create_spreadsheet_error",
                "user_email": user_email,
                "title": title,
                "error": str(e)
            })
            raise
    
    async def _apply_sheet_template(self, service, spreadsheet_id: str, template_name: str):
        """Aplica un template predefinido a la hoja."""
        template = self.sheet_templates[template_name]
        
        requests = []
        
        # Actualizar título de la hoja
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": 0,
                    "title": template['title']
                },
                "fields": "title"
            }
        })
        
        # Agregar headers con formato
        requests.append({
            "updateCells": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(template['headers'])
                },
                "rows": [{
                    "values": [
                        {
                            "userEnteredValue": {"stringValue": header},
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                                "textFormat": {
                                    "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                    "bold": True
                                }
                            }
                        } for header in template['headers']
                    ]
                }],
                "fields": "userEnteredValue,userEnteredFormat"
            }
        })
        
        # Agregar filas de ejemplo basadas en el template
        if template_name == "budget":
            example_data = [
                ["Marketing", "5000", "4500", "=B2-C2", "=D2/B2"],
                ["Ventas", "10000", "12000", "=B3-C3", "=D3/B3"],
                ["Operaciones", "15000", "14200", "=B4-C4", "=D4/B4"]
            ]
        elif template_name == "sales_report":
            example_data = [
                ["Producto A", "100", "25", "=B2*C2", "Enero"],
                ["Producto B", "75", "40", "=B3*C3", "Enero"],
                ["Producto C", "120", "15", "=B4*C4", "Enero"]
            ]
        else:
            example_data = [
                ["Ejemplo 1", "Datos", "Muestra", "Info", "Demo"],
                ["Ejemplo 2", "Datos", "Muestra", "Info", "Demo"]
            ]
        
        for i, row_data in enumerate(example_data, start=1):
            requests.append({
                "updateCells": {
                    "range": {
                        "sheetId": 0,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(row_data)
                    },
                    "rows": [{
                        "values": [
                            {"userEnteredValue": {"stringValue": str(cell)}}
                            for cell in row_data
                        ]
                    }],
                    "fields": "userEnteredValue"
                }
            })
        
        # Ejecutar requests
        await self._execute(
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            )
        )
    
    async def write_data(self, user_email: str, spreadsheet_id: str,
                        range_name: str, values: List[List[Any]],
                        value_input_option: str = "USER_ENTERED") -> bool:
        """
        Escribe datos en una hoja
        
        Args:
            user_email: Email del usuario
            spreadsheet_id: ID de la hoja
            range_name: Rango donde escribir (ej: "A1:C3")
            values: Datos a escribir
            value_input_option: Cómo interpretar los valores
            
        Returns:
            True si se escribió exitosamente
        """
        try:
            service = await self._get_sheets_service(user_email)
            
            body = {
                'values': values
            }
            
            result = await self._execute(
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    body=body
                )
            )
            
            updated_cells = result.get('updatedCells', 0)
            
            logger.info({
                "event": "data_written",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "updated_cells": updated_cells
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "write_data_error",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "error": str(e)
            })
            return False
    
    async def read_data(self, user_email: str, spreadsheet_id: str,
                       range_name: str) -> List[List[str]]:
        """
        Lee datos de una hoja
        
        Args:
            user_email: Email del usuario
            spreadsheet_id: ID de la hoja
            range_name: Rango a leer
            
        Returns:
            Lista de listas con los datos
        """
        try:
            service = await self._get_sheets_service(user_email)
            
            result = await self._execute(
                service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                )
            )
            
            values = result.get('values', [])
            
            logger.info({
                "event": "data_read",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "rows_read": len(values)
            })
            
            return values
            
        except Exception as e:
            logger.error({
                "event": "read_data_error",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "error": str(e)
            })
            return []
    
    async def create_chart(self, user_email: str, spreadsheet_id: str,
                          chart_type: str, data_range: str,
                          title: str, sheet_id: int = 0) -> bool:
        """
        Crea un gráfico en la hoja
        
        Args:
            user_email: Email del usuario
            spreadsheet_id: ID de la hoja
            chart_type: Tipo de gráfico ("COLUMN", "PIE", "LINE", etc.)
            data_range: Rango de datos para el gráfico
            title: Título del gráfico
            sheet_id: ID de la hoja donde insertar
            
        Returns:
            True si se creó exitosamente
        """
        try:
            service = await self._get_sheets_service(user_email)
            
            requests = [{
                "addChart": {
                    "chart": {
                        "spec": {
                            "title": title,
                            "basicChart": {
                                "chartType": chart_type,
                                "legendPosition": "BOTTOM_LEGEND",
                                "axis": [
                                    {
                                        "position": "BOTTOM_AXIS",
                                        "title": "Categorías"
                                    },
                                    {
                                        "position": "LEFT_AXIS",
                                        "title": "Valores"
                                    }
                                ],
                                "domains": [
                                    {
                                        "domain": {
                                            "sourceRange": {
                                                "sources": [{
                                                    "sheetId": sheet_id,
                                                    "startRowIndex": 0,
                                                    "endRowIndex": 10,
                                                    "startColumnIndex": 0,
                                                    "endColumnIndex": 1
                                                }]
                                            }
                                        }
                                    }
                                ],
                                "series": [
                                    {
                                        "series": {
                                            "sourceRange": {
                                                "sources": [{
                                                    "sheetId": sheet_id,
                                                    "startRowIndex": 0,
                                                    "endRowIndex": 10,
                                                    "startColumnIndex": 1,
                                                    "endColumnIndex": 2
                                                }]
                                            }
                                        }
                                    }
                                ]
                            }
                        },
                        "position": {
                            "overlayPosition": {
                                "anchorCell": {
                                    "sheetId": sheet_id,
                                    "rowIndex": 12,
                                    "columnIndex": 0
                                }
                            }
                        }
                    }
                }
            }]
            
            await self._execute(
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": requests}
                )
            )
            
            logger.info({
                "event": "chart_created",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "chart_type": chart_type,
                "title": title
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "create_chart_error",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "error": str(e)
            })
            return False
    
    async def add_formulas(self, user_email: str, spreadsheet_id: str,
                          formulas: Dict[str, str]) -> bool:
        """
        Agrega fórmulas a celdas específicas
        
        Args:
            user_email: Email del usuario
            spreadsheet_id: ID de la hoja
            formulas: Dict con rango:fórmula
            
        Returns:
            True si se agregaron exitosamente
        """
        try:
            service = await self._get_sheets_service(user_email)
            
            requests = []
            
            for range_name, formula in formulas.items():
                requests.append({
                    "updateCells": {
                        "range": self._parse_range(range_name),
                        "rows": [{
                            "values": [{
                                "userEnteredValue": {"formulaValue": formula}
                            }]
                        }],
                        "fields": "userEnteredValue"
                    }
                })
            
            if requests:
                await self._execute(
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={"requests": requests}
                    )
                )
            
            logger.info({
                "event": "formulas_added",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "formulas_count": len(formulas)
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "add_formulas_error",
                "user_email": user_email,
                "spreadsheet_id": spreadsheet_id,
                "error": str(e)
            })
            return False
    
    def _parse_range(self, range_str: str) -> Dict[str, int]:
        """Convierte un rango A1 a formato de API."""
        # Implementación simplificada para A1
        if range_str == "A1":
            return {
                "sheetId": 0,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": 1
            }
        # Agregar más lógica según necesidad
        return {}
    
    async def create_analytics_dashboard(self, user_email: str, title: str,
                                       data: List[Dict[str, Any]],
                                       folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Crea un dashboard de analytics automático
        
        Args:
            user_email: Email del usuario
            title: Título del dashboard
            data: Datos para el dashboard
            folder_id: Carpeta donde guardar
            
        Returns:
            Dict con información del dashboard creado
        """
        try:
            # Crear hoja con template analytics
            sheet_info = await self.create_spreadsheet(
                user_email, title, "analytics_dashboard", folder_id
            )
            
            spreadsheet_id = sheet_info['spreadsheet_id']
            
            # Preparar datos para la hoja
            sheet_data = [["Métrica", "Valor", "Objetivo", "Variación", "Tendencia"]]
            
            for item in data:
                row = [
                    item.get('metric', ''),
                    str(item.get('value', 0)),
                    str(item.get('target', 0)),
                    f"=B{len(sheet_data)+1}-C{len(sheet_data)+1}",
                    item.get('trend', '→')
                ]
                sheet_data.append(row)
            
            # Escribir datos
            await self.write_data(
                user_email, spreadsheet_id, 
                f"A1:E{len(sheet_data)}", sheet_data
            )
            
            # Crear gráfico
            await self.create_chart(
                user_email, spreadsheet_id, "COLUMN",
                f"A1:B{len(sheet_data)}", "Dashboard de Métricas"
            )
            
            logger.info({
                "event": "analytics_dashboard_created",
                "user_email": user_email,
                "title": title,
                "spreadsheet_id": spreadsheet_id,
                "metrics_count": len(data)
            })
            
            return sheet_info
            
        except Exception as e:
            logger.error({
                "event": "create_analytics_dashboard_error",
                "user_email": user_email,
                "title": title,
                "error": str(e)
            })
            raise

# Instancia global del servicio
google_sheets_service = GoogleSheetsService()
