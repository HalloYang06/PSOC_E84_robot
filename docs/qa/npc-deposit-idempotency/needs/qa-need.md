# QA NPC 结构化需求

why: 验证能力工坊从 NPC 默认需求目录读取结构化 Need，并按路径幂等。
required capability: 平台 QA
expected output: 第二次索引时不会重复创建需求队列项。
risk: low
priority: P2
module: skill-forge-qa

- 需求必须只新增一次。
- 第二次索引应显示跳过已入库记录。
