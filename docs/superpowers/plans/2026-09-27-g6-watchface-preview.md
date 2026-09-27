# G6 Watchface Interactive Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma preview local e interativa que reproduza o watchface do G6/Trek 1 em 466×466 pixels, usando os mesmos componentes e posições do BIN real.

**Architecture:** A aplicação será uma página estática sem servidor, composta por HTML, CSS e JavaScript Canvas 2D. Ela carregará os PNGs extraídos e `dial_desc.json`, desenhará as camadas na ordem do firmware e atualizará ponteiros e indicadores em tempo real. O compilador Python e o BIN continuarão separados: a preview serve para validar o design antes de gerar outro BIN.

**Tech Stack:** HTML5, CSS3, JavaScript sem framework, Canvas 2D, PNGs RGBA/RGB565 extraídos, JSON de configuração. Python existente para compilação e validação do BIN.

**Spec:** `g6-cat-gauge-transfer/KNOWLEDGE.md`, `g6-cat-gauge-transfer/source/README.md` e `g6-cat-gauge-transfer/source/dial_desc.json`.

## Global Constraints

- A tela lógica deve ser 466×466 pixels, correspondente ao layout AM05 G6 `0.0_AM05_G6_11448.bin`.
- A ordem de composição deve ser: `background` → `battery` → `steps` → `progress` → `hour` → `minute` → `second` (conforme `dial_desc.json`).
- As posições e pontos de rotação devem vir de `dial_desc.json`, sem números duplicados no JavaScript.
- A preview digital é apenas simulada até que os blocos de dígitos sejam obtidos de um BIN original compatível.
- Não alterar OTA, firmware, resource update ou qualquer função de restauração do relógio.
- O resultado deve funcionar abrindo `preview/index.html` localmente, sem dependências externas ou servidor.

---

### Task 1: Definir o modelo de configuração e os assets

**Files:**
- Create: `g6-cat-gauge-transfer/preview/config.js`
- Create: `g6-cat-gauge-transfer/preview/assets/` com cópias dos PNGs usados
- Test: `g6-cat-gauge-transfer/preview/preview-smoke.html`

**Interfaces:**
- Produces `WATCHFACE_CONFIG`, com `width`, `height`, caminhos dos assets e blocos derivados de `dial_desc.json`.
- `WATCHFACE_CONFIG.layers` deve conter `background`, `battery`, `steps`, `progress`, `hour`, `minute` e `second`.

- [ ] **Step 1: Escrever o teste de carregamento**

```html
<script type="module">
  import { WATCHFACE_CONFIG } from './config.js';
  if (WATCHFACE_CONFIG.width !== 466 || WATCHFACE_CONFIG.height !== 466) throw new Error('canvas size');
  for (const name of ['background', 'hour', 'minute', 'second']) {
    if (!WATCHFACE_CONFIG.layers[name].src) throw new Error(`missing ${name}`);
  }
  document.body.textContent = 'PASS';
</script>
```

- [ ] **Step 2: Executar o teste**

Abrir `preview-smoke.html` no navegador e confirmar `PASS` no corpo da página.

- [ ] **Step 3: Implementar a configuração**

Copiar os assets de `g6-cat-gauge-transfer/assets/` para `preview/assets/` e declarar os caminhos, dimensões, posições e centros de rotação conforme `source/dial_desc.json`.

**Assets necessários:**
- `background.png` (466×466, RGB) — fundo do watchface
- `battery_strip.png` (110×110, RGBA, 6 frames) — indicador de bateria
- `steps.png` (12×18, RGBA, 10 frames) — indicador de passos
- `progress2.png` (110×110, RGBA, 11 frames) — indicador de progresso
- `arm_hour.png` (18×132, RGBA) — ponteiro das horas
- `arm_minute.png` (16×182, RGBA) — ponteiro dos minutos
- `arm_second.png` (28×256, RGBA) — ponteiro dos segundos

**Nota:** `prev.png` (280×280) é uma imagem de preview gerada pelo compilador, não é uma camada do watchface. Não deve ser incluída na composição.

- [ ] **Step 4: Reexecutar o teste**

Abrir a página novamente e confirmar que todos os assets obrigatórios são encontrados.

---

### Task 2: Criar o compositor Canvas

**Files:**
- Create: `g6-cat-gauge-transfer/preview/index.html`
- Create: `g6-cat-gauge-transfer/preview/preview.js`
- Create: `g6-cat-gauge-transfer/preview/preview.css`
- Test: `g6-cat-gauge-transfer/preview/compositor-smoke.html`

**Interfaces:**
- `loadImage(src): Promise<HTMLImageElement>` carrega uma imagem.
- `drawStaticLayers(ctx, images, state)` desenha fundo e indicadores.
- `drawHand(ctx, image, block, angle)` desenha um ponteiro no centro correto.
- `renderWatchface(ctx, images, state)` compõe um frame completo.

- [ ] **Step 1: Escrever o teste de composição**

```js
const canvas = document.createElement('canvas');
canvas.width = canvas.height = 466;
const ctx = canvas.getContext('2d');
await renderWatchface(ctx, images, { hour: 10, minute: 8, second: 30, battery: 4, steps: 5, progress: 6 });
// Verificar múltiplos pontos para evitar falso negativo com fundos transparentes
const points = [[233, 233], [100, 100], [366, 366], [100, 366], [366, 100]];
let hasVisiblePixel = false;
for (const [x, y] of points) {
  if (ctx.getImageData(x, y, 1, 1).data[3] > 0) { hasVisiblePixel = true; break; }
}
if (!hasVisiblePixel) throw new Error('no visible pixels in canvas');

// Verificar se os ponteiros estão visíveis em posições esperadas
// Para 10:08:30, o ponteiro das horas deve estar próximo ao 10, etc.
// Verificar pixels nas bordas do canvas onde os ponteiros devem aparecer
const handPoints = [[233, 100], [233, 366], [100, 233], [366, 233]];
let handPixels = 0;
for (const [x, y] of handPoints) {
  if (ctx.getImageData(x, y, 1, 1).data[3] > 0) handPixels++;
}
if (handPixels < 2) throw new Error('hands not visible in expected positions');
```

- [ ] **Step 2: Executar o teste e confirmar falha inicial**

Abrir `compositor-smoke.html`; antes da implementação, o navegador deve indicar que `renderWatchface` não existe.

- [ ] **Step 3: Implementar o compositor mínimo**

Desenhar `background.png` em 0,0. Usar `ctx.save()`, `ctx.translate()`, `ctx.rotate()` e `ctx.drawImage()` para os três ponteiros, respeitando os centros `ctx/cty`. Desenhar indicadores somente quando o estado tiver índice válido.

**Fórmula de rotação dos ponteiros:**

```js
// ctx/cty são offsets relativos ao centro do sprite (não coordenadas absolutas)
// O ponteiro é desenhado com o centro de rotação na posição (posx, posy)
function drawHand(ctx, image, block, angle) {
  const centerX = block.posx;
  const centerY = block.posy;
  ctx.save();
  ctx.translate(centerX, centerY);
  ctx.rotate(angle * Math.PI / 180); // graus para radianos
  // O sprite é deslocado para que o ponto de rotação (ctx, cty) fique na origem
  ctx.drawImage(image, -block.ctx, -block.cty);
  ctx.restore();
}
```

**Ângulos dos ponteiros (sentido horário, 0° = 12h):**
- `hourAngle = (hour % 12) * 30 + minute * 0.5`
- `minuteAngle = minute * 6 + second * 0.1`
- `secondAngle = second * 6`

**Nota:** Os sprites podem ter deslocamento angular inicial diferente de 0°. Verificar visualmente com a imagem de referência `preview-with-official-hands.png` e ajustar se necessário.

- [ ] **Step 4: Executar o teste**

Abrir `compositor-smoke.html` e confirmar que o centro possui pixels não transparentes e que não há erro no console.

**Tratamento de erros obrigatório:**
- Se um PNG não carregar, exibir mensagem de erro no console e no canvas (não falhar silenciosamente)
- Se o navegador não suportar Canvas 2D, exibir mensagem alternativa
- Validar que os índices dos indicadores estão dentro dos limites antes de desenhar

---

### Task 3: Adicionar controles e atualização em tempo real

**Files:**
- Modify: `g6-cat-gauge-transfer/preview/index.html`
- Modify: `g6-cat-gauge-transfer/preview/preview.js`
- Modify: `g6-cat-gauge-transfer/preview/preview.css`
- Test: `g6-cat-gauge-transfer/preview/state-smoke.html`

**Interfaces:**
- `createDefaultState(): WatchfaceState` retorna hora, bateria, passos, progresso e modo digital.
- `setState(partial): void` atualiza o estado e renderiza.
- `startClock(): number` inicia o relógio usando a hora local.
- `stopClock(): void` encerra o temporizador.

- [ ] **Step 1: Escrever o teste de estado**

```js
const state = createDefaultState();
if (state.battery < 0 || state.battery > 5) throw new Error('battery range');
setState({ hour: 3, minute: 15, second: 0 });
if (getState().hour !== 3 || getState().minute !== 15) throw new Error('state update');
```

- [ ] **Step 2: Executar o teste**

Abrir `state-smoke.html` e confirmar falha até as funções de estado existirem.

- [ ] **Step 3: Implementar controles**

Adicionar controles para hora manual, relógio em tempo real, bateria, passos, progresso e alternância da hora digital conceitual. Os índices devem ser limitados aos frames disponíveis: bateria 0–5, passos 0–9 e progresso 0–10.

- [ ] **Step 4: Executar o teste e testar manualmente**

Confirmar atualização do canvas ao alterar cada controle e que o relógio avança um segundo sem recarregar a página.

---

### Task 4: Comparação visual e exportação

**Files:**
- Modify: `g6-cat-gauge-transfer/preview/index.html`
- Modify: `g6-cat-gauge-transfer/preview/preview.js`
- Modify: `g6-cat-gauge-transfer/preview/preview.css`
- Create: `g6-cat-gauge-transfer/preview/README.md`
- Test: `g6-cat-gauge-transfer/preview/export-smoke.html`

**Interfaces:**
- `exportPng(): void` baixa o canvas como `g6-watchface-preview.png`.
- `toggleDigitalConcept(enabled): void` mostra ou oculta a camada digital simulada.
- `toggleReference(enabled): void` mostra a imagem de referência ao lado do canvas.

- [ ] **Step 1: Escrever o teste de exportação**

```js
const link = exportPng();
if (!link || !link.href.startsWith('blob:')) throw new Error('PNG export failed');
```

- [ ] **Step 2: Implementar exportação e comparação**

Adicionar botão de download, modo de referência com `preview-with-official-hands.png` e a camada digital explicitamente marcada como conceito.

- [ ] **Step 3: Executar a verificação visual**

Abrir `index.html`, testar todos os controles, exportar PNG e comparar o resultado com `preview-with-official-hands.png`.

- [ ] **Step 4: Documentar o uso**

Registrar no `preview/README.md` como abrir a página, quais dados são reais do BIN, quais são simulados e como gerar uma nova imagem para o compilador.

---

### Task 5: Integrar a preview ao ciclo BIN/APK

**Files:**
- Modify: `g6-cat-gauge-transfer/source/README.md`
- Modify: `g6-cat-gauge-transfer/README.md`
- Create: `g6-cat-gauge-transfer/preview/validate-preview-assets.py`

**Interfaces:**
- `validate-preview-assets.py` deve verificar que cada asset referenciado existe, que o canvas é 466×466 e que os nomes dos blocos coincidem com `dial_desc.json`.

- [ ] **Step 1: Criar validação de assets**

Usar somente a biblioteca padrão Python para ler JSON e verificar caminhos, evitando dependências novas.

- [ ] **Step 2: Executar validação**

```bash
python3 g6-cat-gauge-transfer/preview/validate-preview-assets.py
```

Esperado: `preview assets: PASS`.

- [ ] **Step 3: Atualizar documentação**

Documentar o fluxo: editar a preview, exportar assets, executar o compilador existente, conferir os oito blocos e somente então montar o APK.

- [ ] **Step 4: Verificação final**

Abrir a preview, executar a validação de assets e verificar que o BIN original continua inalterado.

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Rotação incorreta dos ponteiros | Validar visualmente com `preview-with-official-hands.png` após implementar |
| Sprites com deslocamento angular diferente de 0° | Ajustar fórmula de rotação após comparação visual |
| Preview não corresponder ao BIN compilado | Usar `validate-preview-assets.py` para garantir que os assets são idênticos |
| Performance lenta | Usar `requestAnimationFrame` e redesenhar apenas quando o estado mudar |
| Diferenças de cor entre preview e BIN | Verificar perfis de cor dos PNGs (RGB565 vs RGBA) |
