"""Spike 02 labelled data.

Labels follow the ZKC definitions:
- static  : objective / timeline / long-lived fact ("此刻可信，未来可更新，生命周期较长")
- dynamic : survival-type, tied to current attention, decays fast ("此刻有用，易腐化，短生命周期")
- None    : genuinely ambiguous — the router SHOULD abstain rather than guess.
"""

# --- Route definitions: utterances the router matches against ---
ROUTES = {
    "static": [
        "PostgreSQL 的 MVCC 通过事务 ID 与快照实现一致性读",
        "RDF 1.2 命名图支持语句级别的溯源",
        "TCP 三次握手用于建立连接并同步序列号",
        "注意力机制的本质是对加权求和",
        "双时态建模包含有效时间与事务时间两个维度",
        "Go 语言的 goroutine 由 runtime 调度到系统线程",
        "知识图谱常用 RDF 与 OWL 来表达本体和约束",
        "指数衰减的半衰期指强度减半所需时间",
        "向量数据库的 HNSW 是一种多层近邻图索引",
    ],
    "dynamic": [
        "今天下午和客户对齐一下交付时间",
        "本周要完成这个 spike 的校准实验",
        "刚开完会，决定把接口改成 v2",
        "这周关注的论文还没读完",
        "项目联调卡在鉴权问题上，需要今天解决",
        "明天上线前必须完成回归测试",
        "临时插入的需求，排期要重新调整",
        "和团队的一对一改到周五下午",
        "这个 bug 阻塞了发布，优先处理",
    ],
}

# --- Held-out evaluation set (ground truth) ---
# label None == the router should abstain
EVAL_SET = [
    # --- static ---
    ("Pgvector 的 HNSW 索引在过滤后需要迭代扫描", "static"),
    ("MVCC 中旧版本元组通过 vacuum 回收", "static"),
    ("CRDT 通过可交换的合并函数保证最终一致", "static"),
    ("Bitemporal 的 valid time 描述事实何时为真", "static"),
    ("Leiden 算法用于社区检测并支持层次结构", "static"),
    ("Pydantic 用于在运行时校验数据结构的类型", "static"),
    ("倒排索引把词项映射到包含它的文档列表", "static"),
    ("OWL 可以定义类的层次与属性约束", "static"),
    ("半衰期越长表示衰减越慢", "static"),
    ("Arrow 是一种列式内存格式", "static"),
    ("RRF 融合多路召回结果时不依赖分数归一化", "static"),
    ("事务的 ACID 中 I 表示隔离性", "static"),
    # --- dynamic ---
    ("下周一前把方案发给对方确认", "dynamic"),
    ("这个会刚结束，结论是先搁置", "dynamic"),
    ("本周的进度落后了，需要加班赶一下", "dynamic"),
    ("客户临时加了个需求，今天要评估", "dynamic"),
    ("我在跟进这个项目的联调问题", "dynamic"),
    ("明天的评审材料还没准备", "dynamic"),
    ("这周要读完这三篇并做笔记", "dynamic"),
    ("刚才对齐的结论是延后到下个迭代", "dynamic"),
    ("这个线上问题今天必须定位", "dynamic"),
    ("和对方的沟通定在后天上午", "dynamic"),
    ("当前正在推进的任务卡在依赖上", "dynamic"),
    ("这次分享的 PPT 周五要定稿", "dynamic"),
    # --- ambiguous: should abstain ---
    ("这个还不错", None),
    ("记得处理一下", None),
    ("下周再说", None),
    ("看看情况", None),
    ("有点意思", None),
    ("先放着", None),
    ("嗯", None),
    ("到时候再定", None),
]

# --- Calibration set (used to learn the threshold; separate from EVAL_SET) ---
CALIB_SET = [
    ("Embedding 的余弦相似度衡量向量方向差异", "static"),
    ("WAL 用于保证崩溃后的数据可恢复", "static"),
    ("图的邻接表用 CSR 格式可以压缩存储", "static"),
    ("SHACL 用于校验 RDF 数据是否满足形状", "static"),
    ("今天要跟对方同步一下进展", "dynamic"),
    ("手头这个事这周得收尾", "dynamic"),
    ("刚才开会定下来的方案有变", "dynamic"),
    ("这个事情优先级提到最高", "dynamic"),
    ("随便", None),
    ("再看看", None),
    ("不一定", None),
    ("大概吧", None),
]
