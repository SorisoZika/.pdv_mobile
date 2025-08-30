const robot = require('robotjs');

// Dá um tempo para você abrir a janela correta
console.log('Você tem 5 segundos para focar na janela do caixa...');
setTimeout(() => {
  // Etapa 1: digita "112" e pressiona Tab
  robot.typeString('112');
  robot.keyTap('tab');

  // Aguarda 3 segundos antes da próxima etapa
  setTimeout(() => {
    // Etapa 2: digita fiscal e senha
    robot.typeString('377316'); // fiscal
    robot.typeString('1829');   // senha
    console.log('Dados enviados com sucesso!');
  }, 3000);
}, 5000);
