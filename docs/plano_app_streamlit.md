# Plano: app Streamlit da modelagem do Sean

> Planejado em 20/10/2026 e implementado no mesmo dia. A seção 8 registra o que mudou em relação ao plano.

**Objetivo:** um webapp em que se troca a modelagem (cenário, noção de caso, atividade, filtros, dia) e se vê na hora o que sai dela: o **DFG**, as **métricas** (as do Sean e as do log) e o **event log**. Serve para decidir qual modelagem seguir antes da descoberta de processos e da predição.

**Princípios**

- O Notebook 4 continua sendo o registro da pesquisa. O app é código novo e não depende dele.
- O app nunca lê `dados/` (16 GB). Ele parte dos alertas já extraídos.
- Os valores padrão reproduzem o Sean literal.
- Tudo é recalculado ao vivo. Com DuckDB, cada modelagem leva menos de 1 s, então não há nada pré-computado além do arquivo de alertas.

---

## 1. Modelo mental: o que o Notebook 4 faz

```
dados/{lab,real}_events.parquet              252 M eventos, 16 GB
  │          só eventos com `rule_technique_id` (os "alertas"), 20 colunas escolhidas
  ▼
saidas/sean/alertas_{lab,real}.parquet        1,71 M + 632 k alertas
  │          higiene dos IDs de técnica (dicionário de correção + regex)
  ▼
UNIVERSO     quais alertas entram (direção, técnica válida, chave do caso não nula)
CASO         que colunas formam o caso
FILTRO       o do Sean: casos com ≥ 2 técnicas distintas
  │
  ▼
event log
  │ RECORTE  dia com mais alertas, IPs ou técnicas (critérios do Sean) ou com mais eventos
  ▼
DFG (Alg. 1 do artigo) → complexidade (eq. 2, 5 e 6 do artigo) → desenho + tabelas
```

O notebook inteiro é **uma função de cinco escolhas**: universo, caso, atividade, filtro e recorte. A §3 (caso = IP de origem + dia, com filtro de direção) é um caso particular da §5.2. Essas escolhas viram os controles do app.

---

## 2. Dados do app

`sean/dados.py` lê `saidas/sean/alertas_{lab,real}.parquet` e gera **`sean/dados/alertas.parquet`**:

- LAB e REAL juntos, com uma coluna `cenario`;
- a higiene da §2 já aplicada (`technique`, `technique_parent`, `tecnica_valida`), mantendo o `technique_id` original;
- uma coluna `ordem` com a posição da linha no arquivo de origem, usada como desempate de timestamps iguais;
- sem `_id` (um hash de 40 caracteres que não comprime), `rule` (redundante) e `canal` (sempre `sysmon`);
- ordenado por cenário, host e ts, em ZSTD.

O arquivo tem ~12 MiB, fica abaixo do limite de 50 MiB do hook e vai para o git, o que dispensa baixar dados no deploy. A exceção está no `.gitignore` (`/dados/` passou a valer só para a pasta da raiz).

**Empates de timestamp:** alertas do mesmo caso com o mesmo timestamp seguem a ordem do arquivo de alertas, o critério da §3 do notebook. Isso afeta de 1 a 6 arestas nos modelos grandes e nenhum veredito. O dia é cortado em UTC, como no notebook.

---

## 3. Parâmetros

| Grupo | Parâmetro | Opções | Padrão |
|---|---|---|---|
| **Universo** | cenário | LAB, REAL, ambos (lado a lado) | LAB |
| | direção | só entrada, só saída, toda conexão, todos os alertas | só entrada |
| | filtros | excluir técnicas, tipos de evento, hosts | nenhum |
| **Caso** | noção de caso | as 8 agregações da §5.2 ou colunas à mão | IP de origem |
| | janela | por dia ou nenhuma (só na personalizada) | por dia |
| **Atividade** | granularidade | técnica, técnica-pai, técnica + programa, tipo de evento Sysmon | técnica |
| **Filtro do Sean** | mínimo de atividades distintas por caso | 1 (desliga) a 10 | 2 |
| **Recorte** | dia | mais técnicas, mais alertas, mais casos, mais eventos após o filtro, escolher, todos | mais técnicas |
| **Critério** | complexidade | V mínimo, V máximo e os coeficientes de ts(V) | 12, 25, 0,0215 e 0,0165 |
| **Desenho** | só visual | programas por vértice, % de arestas visíveis, título | 3, 100%, ligado |

Regras:

- A **complexidade é sempre calculada sobre o modelo completo**. O corte de arestas só limpa o desenho; vértices que ficam sem aresta visível saem do desenho.
- O critério "mais IPs distintos" do Sean vira "mais casos distintos", que é a mesma coisa quando o caso é o IP.
- O filtro do Sean conta **atividades** distintas. Com atividade = técnica, é exatamente o filtro do notebook.
- "Ambos" mostra LAB e REAL **lado a lado**: os períodos não se sobrepõem, então uni-los num log só não faz sentido com recorte por dia.
- Todos os controles ficam na URL (`bind="query-params"`), com o rótulo visível de cada um (`?agr=Host&dir=Todos+os+alertas`). Um link reproduz a modelagem exata.

---

## 4. Telas

**Barra lateral:** os parâmetros, o botão "Voltar ao Sean literal" (recarrega a página sem parâmetros) e o seletor de tema.

**Topo:** as escolhas atuais em etiquetas e duas faixas de cartões: o **event log** (universo, casos antes e depois do filtro, eventos e atividades) e o **modelo do dia** (vértices e arestas, simplicidade V/E contra o limiar ts(V), veredito do Sean).

**Abas** (a aba aberta também fica na URL, e só ela é calculada):

1. **Modelo:** o DFG com título, os programas que disparam cada atividade, cor dos vértices e espessura das arestas pela frequência (escala log), INÍCIO e FIM destacados. Zoom, arrasto, tela cheia, destaque das arestas de um vértice ao passar o mouse e exportação em SVG, PNG (alta resolução, tema claro) e DOT.
2. **Event log:** tabela de casos (eventos, atividades, programas, IPs de destino, início, fim, duração e a sequência comprimida no estilo `T1036  beacon.exe  ×161`), os eventos de um caso ao clicar na linha e download em CSV ou Parquet. Partes do caso iguais em todas as linhas (o único host do LAB, o dia do recorte) são omitidas da tabela.
3. **Por dia:** alertas, casos, técnicas e eventos após o filtro por dia, com os dias escolhidos por cada critério destacados.
4. **Complexidade:** o plano V × V/E com as regiões do Sean e o modelo atual como um ponto, mais as equações.
5. **Comparar agregações:** a §5 ao vivo. Roda as 8 agregações com a atividade e o filtro atuais, sobre todos os alertas (como a §5) ou sobre o universo da barra lateral, e mostra a tabela e os pontos no plano. Clicar numa linha abre aquela agregação na aba Modelo.
6. **Método:** o pipeline, o que cada controle muda, as diferenças em relação ao artigo e as referências.

**Visual:** interface em pt-BR, layout largo, fonte Inter, tema próprio claro e escuro em `.streamlit/config.toml` e uma paleta compartilhada entre os gráficos (Altair) e o DFG.

**Tema:** segue o sistema por padrão. O seletor Sistema/Claro/Escuro grava a escolha onde o próprio Streamlit guarda a dele (`localStorage`), então os dois ficam sincronizados. O app insere `<meta name="darkreader-lock">` e `<meta name="color-scheme" content="light dark">` no `<head>`, para a extensão Dark Reader não escurecer a página por cima do tema do app.

---

## 5. Arquitetura

```
sean/                       núcleo sem Streamlit (o notebook pode importar daqui no futuro)
  constantes.py             SYSMON, FIX, PADRAO, critério do Sean, agregações, rótulos
  dados.py                  higiene e preparo de sean/dados/alertas.parquet; conexão DuckDB
  modelagem.py              Modelagem (dataclass) → universo, caso, filtro, recorte, casos, eventos (SQL)
  dfg.py                    DFG em SQL (lag/lead), critério de complexidade, programas por atividade
  desenho.py                o DFG em DOT (escritor próprio): título, rótulos HTML, estilo por frequência, tema
  paridade.py               confere o núcleo contra as tabelas salvas pelo Notebook 4
  dados/alertas.parquet     ~12 MiB, versionado
interface/                  peças que dependem do Streamlit
  tema.py                   componente de tema (localStorage, matchMedia, Dark Reader) e seletor
  grafo.py                  DFG interativo: Graphviz em WebAssembly no navegador
  graficos.py               plano de complexidade e séries por dia (Altair)
app.py                      uv run streamlit run app.py
.streamlit/config.toml      tema
```

- **DuckDB:** uma conexão em `st.cache_resource`, com a view `alertas` sobre o parquet e um `cursor()` por consulta. Os resultados ficam em `st.cache_data`, com a `Modelagem` (imutável) na chave.
- **Filtro do Sean em SQL:** `count(DISTINCT atividade) OVER (PARTITION BY caso)` sobre o universo; o pior caso medido (LAB, caso = processo) fica em ~0,3 s por consulta.
- **DFG em SQL:** `lag`/`lead` sobre a janela `(PARTITION BY caso ORDER BY ts, ordem)`.
- **Paridade:** `uv run python -m sean.paridade` reproduz exatamente `tabela_dias`, `tabela_modelos`, `tabela_agregacoes` e `tabela_complexidade`, usando os alertas originais e o desempate de cada seção (ordem do arquivo na §3, `_id` na §5).
- **Dependências:** só `streamlit` a mais. O app não usa pm4py, r4pm nem skpm, nem o Graphviz (nem o pacote Python, nem o binário).
- **Tipos:** `app.py`, `util.py`, `sean/` e `interface/` passam no Pyright em modo strict (`uv run pyright`, configurado no `pyproject.toml`); o resto do repositório segue no standard. O grupo `dev` traz `pandas-stubs` e `pyright` para a CLI ver o mesmo que o Pylance.

---

## 6. Etapas de construção

| # | Etapa | Pronto quando |
|---|---|---|
| 1 | `sean/dados.py` e `sean/dados/alertas.parquet` | 1.713.709 + 631.606 alertas, 50/35 técnicas/pais no LAB e 53/33 no REAL |
| 2 | Núcleo (`modelagem`, `dfg`) e `paridade.py` | reproduz exatamente as tabelas do Notebook 4 |
| 3 | Barra lateral, cartões e aba Modelo | DFG enriquecido, com título, para qualquer agregação |
| 4 | Abas Event log, Por dia e Complexidade | as sequências da §5.4 aparecem no app |
| 5 | Comparar agregações, estado na URL, tema, aba Método | um link compartilhado reabre a mesma modelagem |
| 6 | README: seção "O app" | `uv sync` e `uv run streamlit run app.py` funcionam do zero |

---

## 7. Deploy

Os dados são abertos (COMISET no Zenodo, anonimizada pelos autores), então o app pode ser **público e sem autenticação**.

| Opção | Prós | Contras |
|---|---|---|
| Streamlit Community Cloud | grátis, deploy direto do GitHub, sem Docker; o parquet vai no repo; até 2,7 GB de RAM e 2 núcleos (últimos números publicados, de 2024) | o app dorme sem uso; o `pyproject` puxa dependências que o app não usa |
| Hugging Face Spaces | 16 GB de RAM no plano CPU Basic (segundo fontes de 2025) | o SDK Streamlit foi descontinuado em 30/04/2025 (agora via template Docker); relatos conflitantes sobre o plano grátis continuar disponível |
| Servidor próprio (Docker + proxy HTTPS) | controle total | manutenção fica conosco |

Como o DFG e as exportações SVG/PNG são feitos no navegador, o servidor não precisa do Graphviz instalado.

---

## 8. O que mudou em relação ao plano

- **DFG interativo próprio.** O `st.graphviz_chart` desliga o zoom, e um DFG de 580 arestas vira um borrão. O componente `interface/grafo.py` desenha com o Graphviz em WebAssembly (`@hpcc-js/wasm-graphviz`, carregado do jsDelivr) e acrescenta zoom, arrasto, tela cheia e destaque por vértice. Sem internet, ele volta para o `st.graphviz_chart`.
- **Exportação no navegador.** SVG, PNG e DOT são gerados no cliente, então a detecção do `dot` no servidor saiu do plano.
- **DOT sem o pacote `graphviz`.** O app só precisa do texto DOT, então `sean/desenho.py` tem um escritor próprio de ~40 linhas, tipado (o pacote `graphviz` não tem tipos e travava o modo strict). Os notebooks continuam usando o pacote.
- **Teto de 250 arestas no desenho.** O tempo de layout do Graphviz explode com o número de arestas (200: 0,2 s; 300: 1,5 s; 584: 20 s no `dot` nativo, e mais no navegador). Acima de 250, o desenho mostra as 250 mais frequentes e avisa; o interruptor *Sem limite de arestas* desliga o teto.
- **Desempate pela ordem do arquivo**, sem reextrair com `record_number` (seção 2).
- **URL com rótulos**: o Streamlit 1.66 guarda nos parâmetros o rótulo visível de cada controle, não o valor interno.
- **Sem materialização.** Materializar o universo de cada modelagem numa tabela foi testado, mas a contagem por janela já deixou as consultas rápidas o bastante, então ficou de fora.

---

## 9. v2 (backlog)

- **Escolher campos dos alertas e do event log.** O arquivo do app tem ~20 colunas, e trazer um campo novo exige varrer `dados/`, o que é inviável ao vivo. O caminho é extrair offline uma tabela mais larga de alertas, com os campos de presença relevante **entre os alertas** (as tabelas de presença atuais medem todos os eventos: 74 campos com ≥ 1% no LAB e 41 no REAL), partindo das colunas `pm_core` e `ml_feature` do `lab_field_presence_annotated.csv`. No app, esses campos viram chave de caso, atividade ou atributo exibido. A complexidade fica no preparo dos dados, não na interface.
- **Árvore de processos como caso.** O `proc_parent_guid` só existe em 0,26% dos alertas (só no EID 1), então é preciso uma tabela de linhagem (guid → pai → raiz) extraída dos ProcessCreate de `dados/`.
- **Tática ATT&CK como atividade** (visão de kill chain), com um JSON estático do ATT&CK no repo.
- **Janela por hora ou por sessão** (corte por inatividade), como alternativa ao dia.
- **Desempate por `record_number`**, reextraindo os alertas de `dados/`.
- **Clustering** (etapa seguinte do Sean) quando o modelo for complexo.
