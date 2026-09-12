// RF07 — consultas no MongoDB (banco: desafio, colecao: comentarios)
// uso: docker compose exec -T mongo mongosh -u $MONGO_USER -p $MONGO_PASSWORD --authenticationDatabase admin desafio < mongodb/consultas.js

const col = db.comentarios;

// inserir documento
col.insertOne({
  usuario_id: 999, conteudo_id: 1, avaliacao: 5,
  comentario: "Exemplo inserido pelo consultas.js",
  tags: ["exemplo"], data: "2026-09-12",
  categoria: "DevOps & Cloud", titulo: "exemplo", tipo: "Curso",
});

// comentarios de um conteudo
print("--- comentarios do conteudo 1");
col.find({ conteudo_id: 1 }, { _id: 0, usuario_id: 1, avaliacao: 1, comentario: 1 }).forEach(printjson);

// documentos por tag
print("--- documentos com a tag 'lgpd'");
print(col.countDocuments({ tags: "lgpd" }));

// avaliacoes pela nota
print("--- avaliacoes com nota >= 4");
print(col.countDocuments({ avaliacao: { $gte: 4 } }));

// quantidade por categoria
print("--- comentarios por categoria");
col.aggregate([
  { $group: { _id: "$categoria", quantidade: { $sum: 1 }, media: { $avg: "$avaliacao" } } },
  { $sort: { quantidade: -1 } },
]).forEach(printjson);

// remove o documento de exemplo
col.deleteOne({ usuario_id: 999, comentario: "Exemplo inserido pelo consultas.js" });
