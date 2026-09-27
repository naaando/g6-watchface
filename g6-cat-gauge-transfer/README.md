# G6 / Trek 1 — pacote de transferência

Este pacote contém o watchface de teste inspirado no medidor do Need for Speed 2 e o APK do remetente JieLi/SMA preparado para o Galaxy A54.

## Arquivos principais

- `cat-gauge-analog-test.bin`: watchface compilado, usando o layout oficial do G6 `0.0_AM05_G6_11448.bin`.
- `cat-gauge-analog-test.apk`: APK debug instalado no A54; inclui o BIN em `assets/dials/`.
- `preview-with-official-hands.png`: prévia analógica com os ponteiros oficiais recoloridos.
- `preview-digital-concept.png`: conceito visual com hora digital; os dígitos ainda não estão no BIN analógico.
- `assets/`: fundo, ponteiros, sprites e descrição do dial.
- `source/`: script e descrição usados na compilação.
- `sender/`: projeto-fonte do APK, sem `build/` e sem caminhos locais do SDK.
- `KNOWLEDGE.md`: conhecimento técnico consolidado e limites conhecidos.

## Procedimento seguro de transferência

1. Mantenha o G6 carregado e próximo do Galaxy A54.
2. Feche ou desconecte o AuraFit antes de testar outro remetente BLE; dois aplicativos podem disputar a conexão.
3. Abra o APK e use somente scan, conexão, informações do dispositivo e envio do dial.
4. Não use OTA, atualização de firmware, `Update Resource`, restauração ou funções equivalentes.
5. Se o envio falhar, feche o remetente, abra o AuraFit e reconecte o relógio por ele.

O BIN ainda não foi enviado ao G6 nesta sessão. A prévia e a validação binária passaram; a transferência real continua sendo o próximo teste controlado.

## Integridade

Veja `SHA256SUMS.txt`. O APK foi compilado com:

```text
./gradlew assembleDebug -PbuildPython=/opt/homebrew/bin/python3.12
```
