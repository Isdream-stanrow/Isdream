// 模拟数据（先用本地存储）
let riders = [];

// 提交数据
function submitData() {
    const name = document.getElementById('name').value;
    const distance = parseFloat(document.getElementById('distance').value);
    const speed = parseFloat(document.getElementById('speed').value);
    
    if (!name || isNaN(distance) || isNaN(speed)) {
        alert("请填写完整数据！");
        return;
    }

    riders.push({ name, distance, speed });
    updateRanking(); // 提交后立即更新排名
}

// 更新排名
function updateRanking() {
    const sortBy = document.querySelector('select').value;
    const list = document.getElementById('rankList');
    list.innerHTML = '';
    
    // 排序逻辑
    const sorted = [...riders].sort((a, b) => 
        sortBy === 'distance' ? b.distance - a.distance : b.speed - a.speed
    );

    // 显示排名
    sorted.forEach((rider, index) => {
        const li = document.createElement('li');
        li.textContent = `${index+1}. ${rider.name} - ${rider.distance}km @ ${rider.speed}km/h`;
        list.appendChild(li);
    });
}
function exportToCSV() {
  // 从 Firebase 获取数据（需先获取数据）
  const data = [
    { name: "张三", distance: "10km", speed: "15km/h" },
    // ...其他数据
  ];

  // 生成 CSV 格式字符串
  const csvContent = [
    ["姓名", "行程", "均速"],
    ...data.map(row => [row.name, row.distance, row.speed])
  ].map(e => e.join(",")).join("\n");

  // 使用 FileSaver.js 保存文件
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  saveAs(blob, "riding_data.csv");
}
<script src="https://cdnjs.cloudflare.com/ajax/libs/FileSaver.js/2.0.5/FileSaver.min.js"></script>
