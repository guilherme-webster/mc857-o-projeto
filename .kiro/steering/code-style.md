# Estilo de código

## Comentários e docstrings

- Não escreva documentação por conta própria: nada de docstrings de módulo,
  de classe ou de função explicando o que o código faz, nem comentários
  descritivos. Prefira código autoexplicativo. Exemplo do que NÃO fazer:

  ```python
  """Borda HTTP do catalogo: injeta o repository do historico no caso de uso.

  Pilotos e carros vem do banco historico completo (``history.sqlite``), nao de
  uma corrida curada. Se o historico ainda nao foi gerado, devolve 404 com a
  mesma orientacao usada pelos demais endpoints de historico.
  """
  ```

- Só adicione um comentário curto de uma linha quando o usuário pedir, ou para
  registrar um "porquê" não óbvio e indispensável (uma decisão, uma invariante,
  uma peculiaridade), nunca o "o quê" que o próprio código já mostra.
- Não adicione comentários de cabeçalho de seção decorativos (ex.: `# --- ... ---`).
- Não parafraseie a sintaxe: se o comentário só repete o que a linha faz, remova-o.

## Idioma

- Código técnico em inglês: nomes, logs, mensagens de erro, exceções, detalhes
  de respostas HTTP, comentários e qualquer texto voltado a quem desenvolve.
- Português apenas em mensagens destinadas ao usuário final durante a
  simulação, exibidas pelo frontend. O backend não produz texto de usuário
  final; se precisar, o frontend é quem traduz/apresenta.
- Ao editar código existente, converta mensagens técnicas em português para
  inglês.
