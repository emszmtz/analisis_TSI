/**
 * ============================================================
 * DESCARGADOR DE DATOS HISTÓRICOS DE DUKASCOPY
 * ============================================================
 * 
 * INSTRUCCIONES:
 * 1. Instala Node.js desde https://nodejs.org (versión 18+)
 * 2. Abre una terminal en la carpeta donde guardes este archivo
 * 3. Ejecuta: npm install dukascopy-node
 * 4. Ejecuta: node download_dukascopy.js
 * 
 * INSTRUMENTOS DISPONIBLES (ejemplos):
 * 
 * ÍNDICES:
 *   - deuidxeur      → DAX 40 (Alemania)
 *   - usa500idxusd   → S&P 500
 *   - usatechidxusd  → Nasdaq 100
 *   - usa30idxusd    → Dow Jones 30
 *   - gbridxgbp      → FTSE 100 (UK)
 *   - jpnidxjpy      → Nikkei 225 (Japón)
 *   - ausidxaud      → ASX 200 (Australia)
 *   - fraidxeur      → CAC 40 (Francia)
 *   - espidxeur      → IBEX 35 (España)
 *   - eusidxeur      → Euro Stoxx 50
 * 
 * FOREX (principales):
 *   - eurusd, gbpusd, usdjpy, usdchf, audusd, usdcad, nzdusd
 * 
 * COMMODITIES:
 *   - xauusd (Oro), xagusd (Plata), xbrusd (Brent), xtiusd (WTI)
 * 
 * CRYPTO:
 *   - btcusd, ethusd, ltcusd, xrpusd
 * 
 * TIMEFRAMES:
 *   tick, s1, m1, m5, m15, m30, h1, h4, d1, mn1
 * 
 * ============================================================
 */

const { getHistoricalRates } = require('dukascopy-node');
const fs = require('fs');
const path = require('path');

// ╔════════════════════════════════════════════════════════════╗
// ║                    CONFIGURACIÓN                           ║
// ║         Modifica estos valores según necesites             ║
// ╚════════════════════════════════════════════════════════════╝

const DOWNLOADS = [
    // Puedes añadir múltiples descargas aquí
    {
        instrument: 'deuidxeur',      // DAX 40
        timeframe: 'm1',              // 1 minuto
        startDate: '2019-01-01',
        endDate: '2024-12-20',
        outputFile: 'DAX40_1min_2019_2024.csv'
    },
    // Descomenta para descargar más instrumentos:
    // {
    //     instrument: 'usa500idxusd',   // S&P 500
    //     timeframe: 'm1',
    //     startDate: '2019-01-01',
    //     endDate: '2024-12-20',
    //     outputFile: 'SP500_1min_2019_2024.csv'
    // },
    // {
    //     instrument: 'usatechidxusd',  // Nasdaq 100
    //     timeframe: 'm1',
    //     startDate: '2019-01-01',
    //     endDate: '2024-12-20',
    //     outputFile: 'NASDAQ100_1min_2019_2024.csv'
    // },
    // {
    //     instrument: 'eurusd',         // EUR/USD
    //     timeframe: 'm1',
    //     startDate: '2019-01-01',
    //     endDate: '2024-12-20',
    //     outputFile: 'EURUSD_1min_2019_2024.csv'
    // },
];

// ╔════════════════════════════════════════════════════════════╗
// ║                  CÓDIGO DE DESCARGA                        ║
// ║              (No necesitas modificar esto)                 ║
// ╚════════════════════════════════════════════════════════════╝

async function downloadInstrument(config) {
    const { instrument, timeframe, startDate, endDate, outputFile } = config;
    
    console.log('\n' + '═'.repeat(60));
    console.log(`📥 DESCARGANDO: ${instrument.toUpperCase()}`);
    console.log('═'.repeat(60));
    console.log(`   Timeframe: ${timeframe}`);
    console.log(`   Periodo: ${startDate} → ${endDate}`);
    
    const start = new Date(startDate);
    const end = new Date(endDate);
    const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
    console.log(`   Días: ${days}`);
    console.log('   Descargando... (puede tardar varios minutos)');

    try {
        const startTime = Date.now();
        
        const data = await getHistoricalRates({
            instrument: instrument,
            dates: {
                from: start,
                to: end
            },
            timeframe: timeframe,
            format: 'json',
            priceType: 'bid'
        });

        const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
        
        if (data.length === 0) {
            console.log('   ⚠️  No se obtuvieron datos');
            return null;
        }

        console.log(`   ✅ Completado en ${elapsed} minutos`);
        console.log(`   📊 Barras: ${data.length.toLocaleString()}`);

        // Guardar CSV
        const header = 'timestamp,datetime,open,high,low,close,volume\n';
        const rows = data.map(bar => {
            const dt = new Date(bar.timestamp);
            return `${bar.timestamp},${dt.toISOString()},${bar.open},${bar.high},${bar.low},${bar.close},${bar.volume}`;
        }).join('\n');

        fs.writeFileSync(outputFile, header + rows);
        
        const fileSizeMB = (fs.statSync(outputFile).size / (1024 * 1024)).toFixed(2);
        console.log(`   💾 Guardado: ${outputFile} (${fileSizeMB} MB)`);

        // Rango real de datos
        const firstDate = new Date(data[0].timestamp);
        const lastDate = new Date(data[data.length - 1].timestamp);
        console.log(`   📅 Rango: ${firstDate.toISOString().split('T')[0]} → ${lastDate.toISOString().split('T')[0]}`);

        return {
            instrument,
            bars: data.length,
            file: outputFile,
            sizeMB: fileSizeMB
        };

    } catch (error) {
        console.log(`   ❌ Error: ${error.message}`);
        return null;
    }
}

async function main() {
    console.log('\n');
    console.log('╔' + '═'.repeat(58) + '╗');
    console.log('║' + '     DESCARGADOR DE DATOS HISTÓRICOS DUKASCOPY           '.padEnd(58) + '║');
    console.log('║' + '              DATOS GRATUITOS DE CALIDAD                 '.padEnd(58) + '║');
    console.log('╚' + '═'.repeat(58) + '╝');
    
    const results = [];
    const totalStart = Date.now();

    for (const config of DOWNLOADS) {
        const result = await downloadInstrument(config);
        if (result) results.push(result);
    }

    // Resumen final
    const totalElapsed = ((Date.now() - totalStart) / 1000 / 60).toFixed(1);
    
    console.log('\n' + '═'.repeat(60));
    console.log('📋 RESUMEN DE DESCARGAS');
    console.log('═'.repeat(60));
    
    if (results.length === 0) {
        console.log('   No se completó ninguna descarga');
    } else {
        let totalBars = 0;
        let totalSize = 0;
        
        results.forEach(r => {
            console.log(`   ✅ ${r.instrument.toUpperCase()}: ${r.bars.toLocaleString()} barras → ${r.file}`);
            totalBars += r.bars;
            totalSize += parseFloat(r.sizeMB);
        });
        
        console.log('─'.repeat(60));
        console.log(`   Total: ${totalBars.toLocaleString()} barras, ${totalSize.toFixed(2)} MB`);
        console.log(`   Tiempo total: ${totalElapsed} minutos`);
    }
    
    console.log('\n✨ ¡Descarga completada!\n');
}

main().catch(console.error);
