# Out of scope, store address and out-of-hours contact

**Scenario goal:** Accessories redirected (7.1), general store information and when the team is back, on a Saturday afternoon before the Finados holiday.

*Store clock frozen at 2026-10-31T16:20:00 (America/Campo_Grande) · model `sabia-4` · conversation in Brazilian Portuguese, as the store's customers write*

**Customer:** Boa tarde, vocês vendem encordoamento e pedal de guitarra?

**Lia:** Boa tarde! Aqui na Empório da Música a gente trabalha só com instrumentos musicais. Encordoamento e pedais de guitarra são acessórios, então não fazem parte do nosso catálogo 😊

Se quiser dar uma olhada em guitarras, violões, baixos, teclados ou outros instrumentos, é só me falar o que você procura que eu te ajudo!

**Customer:** Ah ok. Qual o endereço da loja? Dá pra passar aí hoje ainda?

<details><summary>Tool calls</summary>

- `store_hours_now({})`
  → `{"agora": "2026-10-31 16:20", "dia_da_semana": "sábado", "aberta_agora": false, "feriado_hoje": false, "proxima_abertura": "terça-feira 03/11 às 09:00"}`

</details>

**Lia:** Nosso endereço é Rua 14 de Maio, 3200 — Centro, Campo Grande/MS.

Hoje é sábado e a loja já fechou, mas abre de novo na terça-feira, dia 03/11, às 09:00. Se quiser, posso já te adiantar informações sobre algum instrumento para quando você passar aqui!
