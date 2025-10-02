// 에너지 절약 수칙 데이터
const energyTips = [
    {
        icon: "💡",
        title: "LED 조명 사용",
        description: "기존 형광등을 LED 조명으로 교체하여 전력 소비를 70% 절약할 수 있습니다."
    },
    {
        icon: "❄️",
        title: "적정 냉난방 온도 유지",
        description: "여름철 26°C, 겨울철 20°C로 설정하여 에너지 사용량을 크게 줄일 수 있습니다."
    },
    {
        icon: "🔌",
        title: "대기전력 차단",
        description: "사용하지 않는 전자기기의 플러그를 뽑거나 멀티탭 스위치를 꺼주세요."
    },
    {
        icon: "🪟",
        title: "자연광 활용",
        description: "낮 시간에는 블라인드를 열어 자연광을 최대한 활용하고 조명 사용을 줄이세요."
    },
    {
        icon: "🖥️",
        title: "컴퓨터 절전모드 설정",
        description: "컴퓨터와 모니터의 절전모드를 설정하여 불필요한 전력 소비를 방지하세요."
    },
    {
        icon: "🚪",
        title: "출입문 관리",
        description: "냉난방 효율을 높이기 위해 출입문을 자주 열어두지 말고 신속히 닫아주세요."
    },
    {
        icon: "🌡️",
        title: "단열 개선",
        description: "창문과 문틈의 단열을 개선하여 냉난방 에너지 손실을 최소화하세요."
    },
    {
        icon: "⏰",
        title: "피크타임 사용 자제",
        description: "전력 수요가 높은 시간대(오후 2-5시)에는 고전력 기기 사용을 자제하세요."
    },
    {
        icon: "🔄",
        title: "정기적인 설비 점검",
        description: "에어컨 필터 청소, 설비 점검을 통해 에너지 효율을 최적화하세요."
    },
    {
        icon: "📊",
        title: "에너지 사용량 모니터링",
        description: "정기적으로 전력 사용량을 확인하고 절약 목표를 설정하여 관리하세요."
    }
];

// 월별 데이터 (실제 데이터)
const monthlyData = {
    "1": { "usage": 197563.47, "cost": 55366215 },
    "2": { "usage": 177796.08, "cost": 49819485 },
    "3": { "usage": 143327.69, "cost": 40147655 },
    "4": { "usage": 132277.06, "cost": 37046848 },
    "5": { "usage": 143383.93, "cost": 40163436 },
    "6": { "usage": 137995.68, "cost": 38651493 },
    "7": { "usage": 191801.46, "cost": 53749395 },
    "8": { "usage": 202643.01, "cost": 56791534 },
    "9": { "usage": 134760.35, "cost": 37743659 },
    "10": { "usage": 142068.13, "cost": 39794222 },
    "11": { "usage": 138033.7, "cost": 38662161 },
    "12": { "usage": 138676.47, "cost": 38842522 }
};

// 숫자 포맷팅 함수
function formatNumber(num) {
    return new Intl.NumberFormat('ko-KR').format(num);
}

// 에너지 절약 수칙 카드 생성
function createTipCards() {
    const tipsGrid = document.getElementById('tips-grid');
    
    energyTips.forEach((tip, index) => {
        const tipCard = document.createElement('div');
        tipCard.className = 'tip-card';
        tipCard.style.animationDelay = `${index * 0.1}s`;
        
        tipCard.innerHTML = `
            <span class="tip-icon">${tip.icon}</span>
            <h3>${tip.title}</h3>
            <p>${tip.description}</p>
        `;
        
        tipsGrid.appendChild(tipCard);
    });
}

// 차트 생성
function createChart() {
    const ctx = document.getElementById('monthlyChart').getContext('2d');
    
    const months = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];
    const usageData = Object.values(monthlyData).map(data => Math.round(data.usage));
    const costData = Object.values(monthlyData).map(data => Math.round(data.cost / 1000000)); // 백만원 단위
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: months,
            datasets: [
                {
                    label: '전력 사용량 (kWh)',
                    data: usageData,
                    backgroundColor: 'rgba(102, 126, 234, 0.6)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2,
                    yAxisID: 'y'
                },
                {
                    label: '전기요금 (백만원)',
                    data: costData,
                    backgroundColor: 'rgba(245, 87, 108, 0.6)',
                    borderColor: 'rgba(245, 87, 108, 1)',
                    borderWidth: 2,
                    type: 'line',
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'A청사 2023년 월별 전력 사용량 및 전기요금',
                    font: {
                        size: 16,
                        weight: 'bold'
                    }
                },
                legend: {
                    position: 'top'
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: '전력 사용량 (kWh)'
                    },
                    ticks: {
                        callback: function(value) {
                            return formatNumber(value) + ' kWh';
                        }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: '전기요금 (백만원)'
                    },
                    grid: {
                        drawOnChartArea: false,
                    },
                    ticks: {
                        callback: function(value) {
                            return value + '백만원';
                        }
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}

// 요약 데이터 업데이트
function updateSummaryData() {
    // 실제 계산된 데이터로 업데이트
    const totalUsage = 1880327.03;
    const totalCost = 526778625;
    const avgUsage = 156693.92;
    const avgCost = 43898219;
    
    document.getElementById('total-usage').textContent = formatNumber(Math.round(totalUsage)) + ' kWh';
    document.getElementById('total-cost').textContent = formatNumber(totalCost) + ' 원';
    document.getElementById('avg-usage').textContent = formatNumber(Math.round(avgUsage)) + ' kWh';
    document.getElementById('avg-cost').textContent = formatNumber(avgCost) + ' 원';
}

// 카드 호버 효과 개선
function addCardInteractions() {
    const summaryCards = document.querySelectorAll('.summary-card');
    const tipCards = document.querySelectorAll('.tip-card');
    
    // 요약 카드 클릭 효과
    summaryCards.forEach(card => {
        card.addEventListener('click', function() {
            this.style.transform = 'scale(0.95)';
            setTimeout(() => {
                this.style.transform = '';
            }, 150);
        });
    });
    
    // 팁 카드 호버 효과 개선
    tipCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.backgroundColor = '#f8f9ff';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.backgroundColor = '';
        });
    });
}

// 스크롤 애니메이션
function addScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);
    
    // 관찰할 요소들 선택
    const animatedElements = document.querySelectorAll('.chart-section, .tips-section');
    animatedElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    });
}

// 차트 컨테이너 높이 설정
function setChartHeight() {
    const chartContainer = document.querySelector('.chart-container');
    chartContainer.style.height = '400px';
}

// 페이지 로드 시 실행
document.addEventListener('DOMContentLoaded', function() {
    updateSummaryData();
    createTipCards();
    setChartHeight();
    
    // 차트는 약간의 지연 후 생성 (DOM이 완전히 로드된 후)
    setTimeout(() => {
        createChart();
        addCardInteractions();
        addScrollAnimations();
    }, 100);
});

// 반응형 차트 리사이즈
window.addEventListener('resize', function() {
    // Chart.js가 자동으로 리사이즈를 처리하므로 별도 처리 불필요
});
