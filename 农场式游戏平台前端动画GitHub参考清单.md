# 农场式游戏平台前端动画 GitHub 参考清单

## 1. 文档目的

这份文档服务于当前 `D:\ai合作产品` 工程，目标不是单纯找“好看的农场游戏”，而是给当前 AI 协作平台的前端改造提供一套**可落地、可裁剪、不会把工程搞复杂**的动画与场景参考。

当前平台要做的是：

- 把首页 `基地总览` 做成更像 QQ 农场 / 庄园经营游戏的主场景
- 保留现有 Next.js 页面系统，不把整个站点重写成纯游戏引擎
- 让动画为“任务、工位、审批、需求、交接、实验楼”服务
- 优先做轻量 2D / 2.5D 效果，不先上重型 3D

结论先说：

**最适合当前项目的路线是：Next.js 继续做页面骨架，只把 `基地总览` 这一层做成 PixiJS 驱动的农场式场景层。**

---

## 2. 最推荐的 GitHub 参考

### 2.1 PixiJS

- GitHub: [pixijs/pixijs](https://github.com/pixijs/pixijs)
- 适合用途：
  - 首页庄园地图
  - 建筑点击反馈
  - 地块高亮
  - 小型 2D 场景动画
- 为什么适合当前项目：
  - 可以只嵌入到一个页面或一个组件，不需要把整个站点推倒重来
  - 和 React/Next.js 混合使用的资料很多，维护成本比整站 Phaser 更低
  - 非常适合做“庄园地图 + 建筑 + 地块 + 粒子”
- 建议在当前项目里的落点：
  - `apps/web/app/base` 作为主要接入点
  - 做一个 `BaseSceneCanvas` 或 `FarmSceneCanvas` 组件

### 2.2 Pixi Game UI

- GitHub: [CyberDex/pixi-game-ui](https://github.com/CyberDex/pixi-game-ui)
- 适合用途：
  - 顶部资源栏
  - 底部工具栏
  - 游戏式弹窗
  - HUD / 状态牌
- 为什么适合当前项目：
  - 你们平台不是纯风景图，而是“游戏化操作台”
  - 这个参考更接近“怎么组织游戏 UI”，不是只给你一个场景
- 建议借鉴的部分：
  - 资源栏布局
  - 工具栏按钮密度
  - 游戏 UI 分层方式
- 不建议照搬的部分：
  - 不要整站都走 canvas UI
  - 详情页、表单页、设置页仍应保持正常 Web 表单

### 2.3 HTML5 Farming Demo

- GitHub: [fariazz/html5-farming-demo](https://github.com/fariazz/html5-farming-demo)
- 适合用途：
  - 农田格子
  - 地块状态切换
  - 作物成长表达
- 为什么适合当前项目：
  - 你们的“任务田块”天然可以映射成农田状态
  - 比起只看商业化农场截图，这个更适合借地块交互逻辑
- 建议映射关系：
  - `未开始任务` -> 待翻地
  - `执行中任务` -> 生长中
  - `待审查任务` -> 待收获
  - `已完成任务` -> 已收获

### 2.4 Harvest Moon Phaser3 Game

- GitHub: [mimikim/harvest-moon-phaser3-game](https://github.com/mimikim/harvest-moon-phaser3-game)
- 适合用途：
  - 农场经营氛围
  - 地图区域组织
  - 轻角色感
- 为什么适合当前项目：
  - 你想要的是“QQ 农场 / 庄园经营”的感觉，这类项目比普通后台模板更对路
  - 它对“地块、建筑、路径、经营节奏”的参考价值高
- 不建议直接照搬：
  - 不建议把当前站点整体改造成 Phaser 路由壳
  - Phaser 更适合参考视觉和交互组织，不适合直接吞掉你现在的 Next.js 页面系统

### 2.5 Water Ripple

- GitHub: [andyvr/water-ripple](https://github.com/andyvr/water-ripple)
- 适合用途：
  - 池塘
  - 河流
  - 点击涟漪
  - 水面轻动效
- 为什么适合当前项目：
  - 你现在的庄园界面里，水面是最容易“出游戏感”的区域
  - 轻量涟漪会比复杂 3D 水体更稳
- 最适合的落点：
  - 首页鱼塘 / 水渠 / 码头区域

### 2.6 Pixi Filters

- GitHub: [pixijs/filters](https://github.com/pixijs/filters)
- 适合用途：
  - 建筑 hover 高亮
  - 异常提示发光
  - 模糊/阴影/发光类反馈
- 为什么适合当前项目：
  - 游戏感很多时候不是靠复杂动画，而是靠“被选中”和“有反馈”
  - 对任务阻塞、审批待确认、Runner 离线等状态特别有用

### 2.7 Pixi Particle Emitter

- GitHub: [pixijs-userland/particle-emitter](https://github.com/pixijs-userland/particle-emitter)
- 适合用途：
  - 收获粒子
  - 升级粒子
  - 审批通过特效
  - 知识沉淀 / 任务完成的小爆点
- 为什么适合当前项目：
  - 你要的是“像游戏”，但不能太花
  - 粒子最适合做瞬时反馈，不会把界面搞得很吵

### 2.8 Sprite Sheet Creator

- GitHub: [blendi-remade/sprite-sheet-creator](https://github.com/blendi-remade/sprite-sheet-creator)
- 适合用途：
  - 工位小人
  - 小动物
  - 巡视角色
  - 待机循环
- 为什么适合当前项目：
  - 如果后面你想把“AI 工位”从卡片升级成带角色的小场景，这类工具会很有用
- 当前建议：
  - 可以先了解，不作为第一阶段必接

---

## 3. 适合当前工程的接入策略

### 3.1 不要整站游戏引擎化

当前工程已经有：

- Next.js 前端
- 多页面结构
- 表单、详情页、任务页、审批页、知识页

所以最稳的路线是：

1. 站点主体继续保持 React / Next.js
2. 只在 `基地总览` 页面嵌入游戏场景层
3. 详情页、配置页、成员页继续使用普通 Web UI

也就是：

```text
普通页面负责管理
基地首页负责“游戏化总控入口”
```

### 3.2 场景层和业务层分开

建议拆成两层：

1. **业务数据层**
   - 任务
   - 工位
   - 审批
   - 需求
   - 交接
   - 实验楼状态

2. **庄园场景层**
   - 建筑
   - 地块
   - 水面
   - 路牌
   - 小动画
   - 高亮反馈

不要把业务逻辑直接写死在动画系统里。

### 3.3 当前最合理的技术组合

推荐组合：

- 页面壳：Next.js
- 场景层：PixiJS
- 动效增强：Pixi Filters + Particle Emitter
- 水面：Water Ripple
- UI 组织参考：Pixi Game UI
- 农田/庄园表达参考：HTML5 Farming Demo + Harvest Moon Phaser3 Game

---

## 4. 功能映射建议

### 4.1 任务农田

适合借鉴：

- `html5-farming-demo`
- `harvest-moon-phaser3-game`

建议映射：

- 空地：未开始任务
- 播种：任务已创建
- 生长：执行中
- 发光待收：待审查
- 收获：已完成
- 虫害/枯萎：阻塞/失败

适合加的动画：

- 土地 hover 高亮
- 成长阶段切换
- 收获粒子
- 阻塞红色闪烁

### 4.2 工位宿舍 / 养殖区

适合借鉴：

- `pixi-game-ui`
- `sprite-sheet-creator`

建议映射：

- 工位在线：活跃小人/灯光
- 上下文偏高：疲劳气泡
- 阻塞：灰掉或警示牌
- 待接手：呼叫铃 / 邮差图标

适合加的动画：

- 轻待机
- 状态气泡
- 呼吸灯
- 任务转移箭头

### 4.3 审批门岗

适合借鉴：

- `pixi-game-ui`
- `pixi filters`

建议映射：

- 待审批：门岗亮灯
- 已通过：金色粒子
- 被驳回：红色牌子
- 高风险：门岗上锁

### 4.4 知识图书馆 / 修仙道场

适合借鉴：

- `pixi filters`
- `particle-emitter`

建议映射：

- 新知识沉淀：书页/光点
- 上下文压缩成功：灵气汇聚
- 决策记录新增：卷轴展开

### 4.5 鱼塘 / 水渠

适合借鉴：

- `water-ripple`

建议映射：

- 实验记录流
- 数据回传流
- 日志流转

这个区域特别适合做“流动感”，但不要绑复杂业务。

---

## 5. 不建议现在直接上的方案

### 5.1 不建议整站 Phaser 化

原因：

- 会让现在的多页面管理界面难维护
- 表单、配置、详情页会变复杂
- 对后续新增功能不友好

### 5.2 不建议先做重 3D

原因：

- 当前目标是可用平台，不是展示型 3D 官网
- 你们还要兼容手机、电脑、开发板浏览器
- 3D 很容易牺牲加载速度和维护性

### 5.3 不建议先做人物自由移动

原因：

- 游戏感不是先靠走路实现的
- 先把建筑、地块、状态反馈做出来更值

---

## 6. 建议的开发优先级

### 第一阶段：先把场景骨架做出来

目标：

- 基地总览从“卡片页”升级成“庄园地图”

建议先做：

1. 建筑区块布局
2. 农田地块
3. 水面区域
4. 顶部资源栏
5. 底部工具栏
6. 点击建筑进入详情页

### 第二阶段：加轻动画

建议加：

1. 建筑 hover
2. 地块成长状态
3. 水面轻涟漪
4. 粒子反馈
5. 阻塞/告警高亮

### 第三阶段：加更强的经营感

建议加：

1. 工位小人/状态泡泡
2. 建筑升级感
3. 收获反馈
4. 路径/流转箭头

---

## 7. 对当前项目最实用的组合结论

如果只选最值得的 5 个 GitHub 参考，建议就是这 5 个：

1. [pixijs/pixijs](https://github.com/pixijs/pixijs)
2. [CyberDex/pixi-game-ui](https://github.com/CyberDex/pixi-game-ui)
3. [fariazz/html5-farming-demo](https://github.com/fariazz/html5-farming-demo)
4. [mimikim/harvest-moon-phaser3-game](https://github.com/mimikim/harvest-moon-phaser3-game)
5. [andyvr/water-ripple](https://github.com/andyvr/water-ripple)

它们分别解决：

- 场景层
- HUD 与按钮层
- 农田交互表达
- 庄园经营氛围
- 水面动效

---

## 8. 最终建议

对当前 AI 协作平台来说，最好的方向不是“把整个站点做成一款完整游戏”，而是：

**把基地总览做成一个真正可点击、可反馈、可切换的农场式庄园地图，让它承担总控入口；其他页面继续保持专业、稳定、好维护的 Web 管理界面。**

这样既能得到你想要的游戏感，也不会把工程复杂度拉爆。

后续如果继续深化，优先顺序建议是：

1. 先做基地总览的 Pixi 场景层
2. 再做任务农田和工位宿舍
3. 再做水面和粒子反馈
4. 最后再考虑工位小人、动物、修仙道场这些增强玩法
