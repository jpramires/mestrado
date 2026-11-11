"""Tabelas fixas do app: nomes do Sysmon, correção dos IDs de técnica, noções de caso e rótulos.

As opções em `SEAN` são as escolhas de Alvarenga et al. (2018); os controles as marcam com "(Sean)".
"""

# https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon#events
SYSMON: dict[int, str] = {
    1: "ProcessCreate",
    2: "FileCreateTime",
    3: "NetworkConnect",
    4: "SysmonServiceState",
    5: "ProcessTerminate",
    6: "DriverLoad",
    7: "ImageLoad",
    8: "CreateRemoteThread",
    9: "RawAccessRead",
    10: "ProcessAccess",
    11: "FileCreate",
    12: "RegistryCreateDelete",
    13: "RegistrySetValue",
    14: "RegistryRename",
    15: "FileCreateStreamHash",
    16: "SysmonConfigChange",
    17: "PipeCreated",
    18: "PipeConnected",
    19: "WmiEventFilter",
    20: "WmiEventConsumer",
    21: "WmiConsumerBinding",
    22: "DnsQuery",
    23: "FileDelete",
    24: "ClipboardChange",
    25: "ProcessTampering",
    26: "FileDeleteDetected",
    27: "FileBlockExecutable",
    28: "FileBlockShredding",
    29: "FileExecutableDetected",
    255: "Error",
}

# ID sujo ou de versão antiga do ATT&CK -> ID atual (Notebook 4, §2)
FIX: dict[str, str] = {
    "1210": "T1210",
    "Port Monitors": "T1547.010",
    "T1546.0082": "T1546.008",
    "T1547.0102": "T1547.010",
    "T1055; Possible Cobalt Strike post-exploitation jobs.": "T1055",
    "T1086": "T1059.001",  # PowerShell
    "T1093": "T1055.012",  # Process Hollowing
    "T1130": "T1553.004",  # Install Root Certificate
    "T1073": "T1574.002",  # DLL Side-Loading
    "T1099": "T1070.006",  # Timestomp
    "T1170": "T1218.005",  # Mshta
    "T1117": "T1218.010",  # Regsvr32
    "T1063": "T1518.001",  # Security Software Discovery
    "T1031": "T1543.003",  # Modify Existing Service
    "T1064": "T1059.005",  # Scripting -> Visual Basic (wscript/cscript)
    "T1175": "T1559.001",  # COM (se for DCOM seria T1021.003)
    "T1089": "T1189",  # ID diz Disabling Security Tools, nome diz Drive-by (T1189)
}

TECNICA_VALIDA = r"^T\d{4}(\.\d{3})?$"  # T1234 ou T1234.567

# critério de complexidade de Alvarenga et al. (2018): eq. 5 (limiar = A·V + B) e eq. 6 (faixa de V)
V_MIN, V_MAX = 12, 25
LIMIAR_A, LIMIAR_B = 0.0215, 0.0165

CENARIOS: dict[str, str] = {"lab": "LAB", "real": "REAL"}

# nome -> (rótulo, valores aceitos do campo `initiated`; None = sem filtro de direção).
# Só os alertas de conexão de rede (EventID 3) têm direção: as três primeiras opções ficam só com eles.
DIRECOES: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "entrada": ("Só conexões de entrada", ("false",)),
    "saida": ("Só conexões de saída", ("true",)),
    "conexoes": ("Só conexões (os dois sentidos)", ("true", "false")),
    "todos": ("Todos os alertas", None),
}

# colunas que podem formar o caso
COLUNAS_CASO: dict[str, str] = {
    "src_ip": "IP de origem",
    "dst_ip": "IP de destino",
    "host": "host",
    "usr": "usuário",
    "proc_name": "programa",
    "proc_guid": "processo",
    "tgt_proc_guid": "processo-alvo",
}

# noções de caso prontas: nome -> (rótulo, colunas que formam o caso, se acrescenta o dia)
AGREGACOES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ip_origem": ("IP de origem", ("src_ip",), True),
    "ip_destino": ("IP de destino", ("dst_ip",), True),
    "par_ips": ("Par de IPs", ("src_ip", "dst_ip"), True),
    "host": ("Host", ("host",), True),
    "usuario": ("Usuário", ("host", "usr"), True),
    "programa": ("Programa", ("host", "proc_name"), True),
    "processo": ("Processo", ("host", "proc_guid"), False),
    "processo_alvo": ("Processo-alvo", ("host", "tgt_proc_guid"), False),
}

ATIVIDADES: dict[str, str] = {
    "technique": "Técnica",
    "technique_parent": "Técnica-pai",
    "technique_proc": "Técnica + programa",
    "event_id": "Tipo de evento Sysmon",
}

# critério de escolha do dia -> rótulo
CRITERIOS: dict[str, str] = {
    "tecnicas": "Mais técnicas distintas",
    "alertas": "Mais alertas",
    "casos": "Mais casos distintos",
    "eventos": "Mais eventos após o filtro",
}

# as escolhas de Alvarenga et al. (2018): noção de caso, direção, atividade e os critérios do dia
SEAN = {"ip_origem", "entrada", "technique", "tecnicas", "alertas", "casos"}
