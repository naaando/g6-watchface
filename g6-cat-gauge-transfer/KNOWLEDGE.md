# Conhecimento consolidado

## Dispositivo e conexão

- Relógio: G6 / Trek 1, identificado pelo AuraFit como firmware V9.0.6.
- Telefone: Galaxy A54 via ADB Wi-Fi (`192.168.1.68:36343` durante a captura).
- O relógio precisa estar em pairing mode para aparecer no scanner JieLi.
- O fluxo que funcionou foi remover do AuraFit, resetar o relógio, testar o scanner e depois refazer o pareamento no AuraFit.

## Protocolos descobertos

- O Watch Test Tool oficial da JieLi encontrou o relógio e inicializou RCSP/JL701N (`sdkFlag=JL701N_WATCH_SDK(9)`).
- A operação de watchface do WatchManager oficial ficou limitada pelo suporte de armazenamento/upgrade do dispositivo.
- O fluxo de watchface usado pelo AuraFit é SMA/SMABLE (`com.szabh.smable3`, `WatchFaceBuilder`), compatível com o caminho usado pelo Fogg para dispositivos AM05.
- Dois watchfaces originais foram extraídos do cache do AuraFit: `0.0_AM05_G6_11359.bin` e `0.0_AM05_G6_11448.bin`.
- O formato do BIN foi decodificado pelo Fogg. O layout usado no teste é o de `11448`, com fundo, faixa de bateria, passos, progresso e três ponteiros.

## Artefato atual

O `cat-gauge-analog-test.bin` usa a arte azul texturizada, ponteiros oficiais do G6 recoloridos e camadas de complicações transparentes. A validação confirmou oito blocos, round-trip de fundo/prévia/ponteiros e transparência das camadas não usadas.

O conceito digital é apenas uma referência visual. Para colocar hora digital no relógio será preciso descobrir o layout de dígitos a partir de outro BIN original e adicionar esses blocos sem alterar o protocolo.

## Limites e segurança

- Não enviar arquivos aleatórios nem usar OTA/firmware/resource update.
- Não afirmar compatibilidade final antes de testar a transferência no G6.
- Se o APK não conectar, primeiro liberar o AuraFit e repetir o scan; depois restaurar o pareamento no AuraFit.
- O patch local em `Fogg/comp_decomp.py` corrige a conversão RGB888→RGB565 para evitar overflow de `numpy.uint8`.

