# 数据源接口、权限与配额说明

两条数据源均为「两段式」：**前半段用官方检索接口拿 id（正门），后半段用网页隐藏接口抠边界（后门）**。

| 来源 | 前半段（名称 → id） | 后半段（id → 边界） | 边界坐标系 |
|---|---|---|---|
| 高德 | 官方 `place/text` | 网页隐藏 `getPoiInfo` | GCJ-02 |
| 百度 | 官方 `place/v2/search` | 隐藏 `qt=ext` | bd09mc |

---

## 密钥配置

密钥走三级来源（优先级从高到低）：配置文件 `keys` 字段 / `key_file` 文件（每行 `字段=值`）/ 环境变量（`AMAP_KEY`、`BAIDU_AK`）。复制 `configs/keys.txt.example` 为 `configs/keys.txt` 填写，或直接用环境变量，无需在终端传密钥；`.gitignore` 默认排除 `configs/keys.txt` 与 `.env`，请勿提交真实密钥。

---

## 一、高德

### 1.1 名称 → id（官方 `place/text`）

```
GET https://restapi.amap.com/v3/place/text
    ?keywords=同济大学&city=上海&output=JSON
    &offset=25&page=1&key=你的Key&extensions=all
```

| 参数 | 说明 |
|---|---|
| `keywords` | 检索关键词（必填） |
| `city` | 城市名/编码/adcode，或「全国」 |
| `key` | 高德「Web 服务」类型 Key |
| `offset` / `page` | 每页条数（≤25）/ 页码 |
| `extensions` | `all` 才返回 type/typecode/keytag 等分类字段 |

工具会自动翻页（`page` 递增、每页 `offset=25`），直到取满 `max_candidates` 个候选或无更多结果。重名场景（如「第一人民医院」「区政府」）候选可能超过一页，翻页可避免漏匹配；`max_candidates` 增大时检索请求数也相应增加，注意配额。

**返回候选 `pois[]`，关键字段**：

| 字段 | 含义 |
|---|---|
| `id` | poi_id（`B001...`），抠边界用 |
| `name` / `type` / `typecode` / `keytag` | 名称 / 三级分类 / 6 位编码 / 标签 |
| `location` | `"lng,lat"` 字符串（**经度在前**） |
| `parent` | 父级/所属片区 id；非空不一定是子面，精确同名目标仍会保留 |

常用 `typecode`：`141201` 高等院校、`141200` 学校（教学楼级）、`141202` 中学、`150500` 地铁站、`150700` 公交站、`090101` 三甲医院、`150905` 停车场。

### 1.2 id → 边界（网页隐藏 `getPoiInfo`）

> 高德网页版已改版为 SSR 架构，旧接口 `detail?id=xxx` 已失效，新版为 `getPoiInfo`。

```
GET https://amap-pc-ssr.amap.com/ssr/api/getPoiInfo?id=B00155QBTK&user_loc=121.47,31.23
```

**响应边界字段**：

```json
{
  "base": {
    "id": "B00155K8FL", "name": "同济大学(四平路校区)",
    "address": "四平路1239号", "tel": "021-65982200;...",
    "typecode": "141201", "type": "141201", "newtype": "141201",
    "adcode": "310110", "citycode": "310000",
    "cityname": "上海市", "districtname": "杨浦区"
  },
  "spec": { "mining_shape": { "shape": "121.385073, 31.27398;121.386898, 31.274173;..." } },
  "bound": "121.385073, 31.27398_121.386898, 31.274173_...",
  "tags": {
    "tag_show_info": ["双一流", "985高校", "211高校"],
    "t_tag_list": ["985大学", "大学", "高等教育"],
    "t_tag": "985大学",
    "tag_display": "985大学"
  }
}
```

- `spec.mining_shape.shape`：**主边界**，`;` 分隔坐标对，每对 `经度, 纬度`（逗号后带空格），GCJ-02。飞地/多校区等多部件 AOI 会把多个环首尾相接成一条序列，工具会按「坐标回到起始点」自动拆分为多个环，构成 Polygon 或 MultiPolygon。
- `bound`：备用边界，`_` 分隔。
- `user_loc`：参考坐标（可选，可由检索 `location` 提供）。
- 点状 POI（厕所/大门/ATM 等）无 `mining_shape`，返回 None。
- `data.base` 的 `typecode`、`type`、`newtype`、`adcode`、`citycode`、`cityname`、`districtname`、`tel` 随边界写入 AOI 属性，均按字符串保存；缺失值保留为空字符串。
- `data.tags` 的 `tag_show_info`、`t_tag_list`、`t_tag`、`tag_display` 随边界写入 AOI 属性；GeoJSON 保留数组，GPKG/Shapefile 将数组转为 JSON 字符串。Shapefile 长字段名使用 `tag_show`、`tag_disp`、`district` 别名。

### 1.3 配额与正规商用渠道

- `place/text`：个人实名认证后**月度配额**（2025-05-20 起取消日配额），免费额度足够研究用途。
- 正规 AOI 边界：`v5/aoi/polyline`（返回 `aois[].polyline`），**属高阶服务，需提交工单开通**；企业级 AOI 数据走高德企业地图。

---

## 二、百度

### 2.1 名称 → uid（官方 `place/v2/search`）

```
GET https://api.map.baidu.com/place/v2/search
    ?query=同济大学&region=上海&output=json&ak=你的AK&scope=2
```

| 参数 | 说明 |
|---|---|
| `query` | 检索关键词（必填） |
| `region` | 行政区划（城市/区县/全国） |
| `ak` | 百度开放平台服务端 AK |
| `scope` | `2` 才返回 tag 等字段，供过滤乱入 |
| `page_size` / `page_num` | 每页条数（≤20）/ 页码（从 0 起） |

工具会自动翻页（`page_size=20`、`page_num` 递增），直到取满 `max_candidates` 个候选或无更多结果；此前只取默认第一页（约 10 条），重名场景容易漏候选。

**返回候选 `results[]`，关键字段**：

| 字段 | 含义 |
|---|---|
| `uid` | poi_id（16~24 位十六进制），抠边界用 |
| `location` | `{lat, lng}` 对象（**纬度在前**） |
| `detail` | `1`=面状主 POI，`0`=附属点（直接丢弃） |
| `detail_info.tag` / `classified_poi_tag` | `一级分类;二级分类` |
| `detail_info.parent_id` | 父级 POI；可能表示所属住宅区，精确同名目标仍会保留 |

### 2.2 uid → 边界（隐藏 `qt=ext`）

```
GET https://map.baidu.com/?newmap=1&qt=ext&uid=<uid>&ext_ver=new&ie=utf-8&l=11
```

- **`ext_ver=new` 是关键开关**：缺失则返回空壳（`content` 缺失、`result.uid=null`、回默认城市信息）。
- 边界在 **`content.geo`**，格式：`N|bbox左下;bbox右上|1-x1,y1,x2,y2,...;`
  - `|` 分隔：分块数 / bbox 两角点 / 多边形数据；
  - `-` 后为各多边形，扁平 `x1,y1,x2,y2` 逗号分隔，首尾闭合；多个 `-` 段（飞地/多部件）会拼成 MultiPolygon；
  - 坐标为 **bd09mc 百度墨卡托**（7~8 位大数字），需 `bd09mc → bd09 → gcj02 → wgs84` 三级转换。

### 2.3 配额与正规商用渠道

| 档位 | 内容 | 价格 |
|---|---|---|
| 免费 | 地点检索（个人开发者） | 100 次/天 |
| 基础搜索服务配额包 | 地点检索等 | 300 元 / 12 万次（有效期 372 天，联系商务） |

- 实测"多 AK + 多 IP"不能累加免费额度，一个 AK 即可。
- 正规 AOI 边界：百度开放平台「区域边界查询」/ AOI 检索 SDK，**高级权限，需工单/商务申请**。

---

## 三、反爬与限流建议

两层接口防护重点不同，不可混用：

| 层 | 风险 | 对策 |
|---|---|---|
| 官方检索接口（place/text、place/v2/search） | 配额耗尽、QPS 限流 | 控制频率，遵守配额 |
| 网页隐藏接口（getPoiInfo、qt=ext） | 反爬（UA/Cookie 检测、滑块、封 IP） | 随机 UA/Cookie、降频 ≥1~3 秒、批量建议代理池 |

工具默认随机 UA + 随机间隔（`request.min_interval`/`request.max_interval`），支持 `request.proxy`、`--resume` 断点续爬。触发人机验证时，可在配置 `headers` 中提供 `amap_cookie` / `baidu_cookie` 及对应 `*_user_agent`，复用浏览器已验证会话；Cookie 与 UA 必须来自同一浏览器。工具识别到 `FAIL_SYS_USER_VALIDATE`、`RGV587_ERROR` 或验证 HTML 后会立即停止，不再进行无效重试。

- **并发**：`request.concurrency` 控制 worker 数（默认 1 串行）。并发下所有请求共享一个限流器，总 QPS 仍受间隔参数控制；官方检索可适度并发，隐藏边界接口较敏感，建议 `concurrency ≤ 2~4`。
- **边界缓存**：按 poi_id 持久化已抠边界（默认开，`cache.enabled`/`cache.dir` 配置）。重复跑同一清单时边界请求命中缓存，既提速也降低被反爬识别的风险；想清空直接删除缓存目录。

高德当前网页版成功 GET 还可能包含 `Bx-Ua`、`Bx-Umidtoken`、`Bx_et`、`X-Csrf-Token`、`X-Adiu` 等动态请求头。仅配置 Cookie 与 UA 仍失败时，可按 `configs/keys.txt.example` 从**同一次成功的 GET `getPoiInfo`** 整组复制；OPTIONS 预检无 Cookie 属于正常现象。动态头只用于边界请求，不用于官方检索，且可能随会话过期。工具不会自动伪造或绕过这些安全校验。

**兜底方案**：高德可用"半人工 F12/Fiddler 抓包"（F12 → Network → 找 `getPoiInfo` → Response 取 `spec.mining_shape.shape`），稳定可控，适合少量地点。

## 四、合规提醒

`getPoiInfo`、`qt=ext` 均为**非公开隐藏接口**，可能随时改版失效，且受平台条款约束。本工具仅供学习研究，**不得商用、不得大规模爬取**。规模化、可商用请走官方高阶服务。
