import React from 'react';

const Stats = () => {
  // 📊 Фейковые данные (потом подключим сюда реальный API с твоего сервера)
  const networkStats = [
    {
        label: 'Total Users',
        value: '14,230',
        trend: '+12%',
        color: 'text-[#00ff9d]', // Неоновый зеленый
        bg: 'bg-[#00ff9d]/20'
    },
    {
        label: 'Volume (All-Time)',
        value: '$1.24B',
        trend: '+5.4%',
        color: 'text-[#00d2ff]', // Циан
        bg: 'bg-[#00d2ff]/20'
    },
    {
        label: 'Total Trades',
        value: '8.4M',
        trend: '+8.1%',
        color: 'text-white/90',  // Белый
        bg: 'bg-white/10'
    },
    {
        label: 'Liquidated (All-Time)',
        value: '$45.2M',
        trend: '+2.1%',
        color: 'text-[#ff4b4b]', // Красный
        bg: 'bg-[#ff4b4b]/20'
    },
  ];

  return (
    <div className="w-full bg-[#080b11] border border-white/5 rounded-3xl flex flex-col shadow-3xl overflow-hidden h-[600px] lg:h-[750px] font-sans">

      {/* 1. ШАПКА КОМПОНЕНТА */}
      <div className="h-16 bg-[#080b11] border-b border-white/5 flex items-center justify-between px-10 shrink-0 z-30 relative">
        <div className="flex items-center gap-8">
          <span className="text-sm font-black tracking-[0.3em] text-blue-500 uppercase">
            Pacifica Stats
          </span>
        </div>
        <div className="text-[10px] text-white/20 uppercase tracking-widest flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#00ff9d] animate-pulse"></span>
          Live Network Data
        </div>
      </div>

      {/* 2. СТРОКА СТАТИСТИКИ (Те самые 4 метрики) */}
      <div className="grid grid-cols-2 md:grid-cols-4 border-b border-white/5 bg-[#0a0e17] shrink-0">
        {networkStats.map((stat, i) => (
          <div
            key={i}
            className="p-6 md:p-8 border-b md:border-b-0 border-r border-white/5 last:border-r-0 flex flex-col justify-center relative overflow-hidden group cursor-default"
          >
            {/* Эффект свечения при наведении */}
            <div className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 ${stat.bg} blur-2xl z-0`} />

            <span className="text-[10px] font-bold tracking-[0.2em] text-white/40 uppercase mb-2 relative z-10">
              {stat.label}
            </span>

            <div className="flex items-baseline gap-3 relative z-10">
              <span className={`text-3xl lg:text-4xl font-light tracking-tighter ${stat.color}`}>
                {stat.value}
              </span>
              <span className="text-xs font-bold text-[#00ff9d]/70">
                {stat.trend}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* 3. КОНТЕЙНЕР ДЛЯ БУДУЩЕГО ГРАФИКА */}
      <div className="flex-grow relative p-8 bg-[#080b11] flex flex-col">

        {/* Панель управления графиком */}
        <div className="flex items-center justify-between mb-6">
           <h3 className="text-white/80 font-medium tracking-widest uppercase text-xs">
             Global Activity Chart
           </h3>
           <div className="flex gap-2 bg-white/5 p-1 rounded-lg border border-white/5">
              <button className="px-4 py-1 text-xs font-medium rounded-md bg-white/10 text-white shadow-inner">24H</button>
              <button className="px-4 py-1 text-xs font-medium rounded-md text-white/30 hover:text-white transition-colors">7D</button>
              <button className="px-4 py-1 text-xs font-medium rounded-md text-white/30 hover:text-white transition-colors">ALL</button>
           </div>
        </div>

        {/* Пустое место под график */}
        <div className="w-full h-full border border-dashed border-white/10 rounded-2xl flex items-center justify-center bg-white/[0.01] relative overflow-hidden group">
          <div className="text-center relative z-10">
            <div className="text-5xl mb-4 opacity-50 transform group-hover:scale-110 transition-transform duration-500">📊</div>
            <div className="text-white/30 text-sm tracking-widest uppercase font-bold">
              Chart Area
            </div>
            <div className="text-white/20 text-xs mt-2">
              Waiting for data integration...
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

export default Stats;