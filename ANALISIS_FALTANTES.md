# Análisis: Dashboard actual vs Informe Looker Studio

## ✅ Lo que YA tenemos implementado

| Sección | Estado | Notas |
|---|---|---|
| Filtros (cuenta, campaña, fecha) | ✅ | Fecha por defecto: último mes completo |
| KPIs base (Gasto, Impresiones, Clics, CTR, CPC, Alcance, Frecuencia) | ✅ | Con tooltips (?) |
| Gráfico diario (barras) | ✅ | Gasto / Impresiones / Clics |
| Tabla Campañas | ✅ | Nivel campaign |
| Tabla Adsets | ✅ | Nivel adset |
| Tabla Anuncios / Creatividades | ✅ | Nivel ad |
| Embudo básico | ✅ | Impresiones → Clics → Compras |
| KPIs de conversión | ✅ | Compras, Valor de compra, ROAS, Costo por compra |
| Gráfico de Ubicación | ⚠️ | Funciona pero sin datos de `publisher_platform` |

## ❌ Lo que FALTA (requiere nuevos campos en Meta API)

| Sección | Campos necesarios | Por qué falta |
|---|---|---|
| **Hold rate vs CTR** | `video_avg_time_watched_actions`, `video_play_actions`, `impressions` | No se piden en la extracción |
| **Ventanas de conversión** | `actions` con `action_attribution_windows` | Meta API lo soporta pero no se usa |
| **Demografía** | `age`, `gender` | Requieren breakdowns |
| **Countries** | `country` | Requiere breakdown |
| **Device / Device brand** | `device_platform`, `platform_position` | Requieren breakdowns |
| **Landing page views** | `actions` con `action_type = 'landing_page_view'` | Se puede extraer de `actions` |
| **Adds to cart** | `actions` con `action_type = 'add_to_cart'` | Se puede extraer de `actions` |
| **Daily budget / pacing** | `daily_budget`, `lifetime_budget` de campaigns | No se extraen |
| **Imagen del anuncio** | `creative.image_url` o `creative.thumbnail_url` | Requiere llamada extra a API |
| **Summary diaria** | Agregación por día | Se puede hacer con queries |

## 🔧 Cómo completar lo que falta

### Prioridad 1 (fácil, usa datos existentes)
- [ ] **Landing page views**: parsear `actions` con `action_type = 'landing_page_view'`
- [ ] **Adds to cart**: parsear `actions` con `action_type = 'add_to_cart'`
- [ ] **Summary diaria**: query agregada por día con todas las métricas
- [ ] **Gráfico Over time**: líneas de conversiones por día

### Prioridad 2 (requiere nuevos campos en Meta API)
- [ ] **Hold rate**: agregar `video_avg_time_watched_actions` y `video_play_actions`
- [ ] **Ventanas de conversión**: usar `action_attribution_windows` en `actions`
- [ ] **Imagen del anuncio**: agregar campo `creative` y extraer URL

### Prioridad 3 (requiere breakdowns en Meta API)
- [ ] **Demografía**: `breakdowns=['age', 'gender']`
- [ ] **Countries**: `breakdowns=['country']`
- [ ] **Device / Device brand**: `breakdowns=['device_platform']`
- [ ] **Placement**: `breakdowns=['publisher_platform', 'platform_position']`

### Prioridad 4 (datos de configuración)
- [ ] **Daily budget / pacing**: extraer de endpoint de campaigns

## 📋 Recomendación

Para tener un dashboard más parecido al informe original, sugiero implementar en este orden:

1. **Landing page views y Adds to cart** (usa `actions` existente)
2. **Summary diaria** (query simple)
3. **Hold rate** (agregar 2 campos a la API)
4. **Placement real** (agregar breakdown `publisher_platform`)
5. **Demografía y dispositivos** (más breakdowns)
