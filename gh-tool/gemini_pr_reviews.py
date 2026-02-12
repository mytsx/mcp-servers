#!/usr/bin/env python3
"""
Senin son "/gemini review" yorumundan sonraki Gemini Code Assist değerlendirmelerini getiren script
"""

import subprocess
import json
import datetime
from typing import List, Dict, Any, Optional
import argparse

class GeminiAfterLastReviewFetcher:
    def __init__(self, repo: str, pr: Optional[int] = None, username: str = None):
        self.repo = repo
        # PR numarası verilmezse son PR'ı bul
        self.pr = pr if pr is not None else self._find_last_pr()
        # Eğer username verilmezse GitHub CLI'dan authenticated user'ı al
        self.username = username or self._get_authenticated_user()
        # Dinamik olarak son "/gemini review" yorumunu bul
        self.last_review_time = self._find_last_gemini_review_request()
    
    def _find_last_pr(self) -> int:
        """Repository'deki son PR numarasını bul"""
        print(f"🔍 {self.repo} için son PR aranıyor...")
        
        cmd = [
            "gh", "pr", "list",
            "--repo", self.repo,
            "--limit", "1",
            "--json", "number",
            "--jq", ".[0].number"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            pr_number = int(result.stdout.strip())
            print(f"✅ Son PR bulundu: #{pr_number}")
            return pr_number
        except (subprocess.CalledProcessError, ValueError):
            print("❌ Son PR bulunamadı.")
            raise ValueError("Son PR bulunamadı. Lütfen --pr parametresini kullanın.")
    
    def _get_authenticated_user(self) -> str:
        """GitHub CLI'dan authenticated user'ı al"""
        try:
            result = subprocess.run(
                ["gh", "api", "user", "--jq", ".login"],
                capture_output=True,
                text=True,
                check=True
            )
            username = result.stdout.strip()
            print(f"✅ GitHub authenticated user: {username}")
            return username
        except subprocess.CalledProcessError:
            print("❌ GitHub CLI authentication bulunamadı.")
            return None
    
    def run_gh_command(self, cmd: List[str]) -> Any:
        """GitHub CLI komutunu çalıştır ve JSON sonucunu döndür"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"❌ GitHub CLI komutu başarısız: {e}")
            print(f"Hata: {e.stderr}")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing hatası: {e}")
            return []
    
    def _find_last_gemini_review_request(self) -> str:
        """Son '/gemini review' yorumunun tarihini bul"""
        print(f"🔍 {self.repo} PR #{self.pr} için son '/gemini review' yorumu aranıyor...")
        
        cmd = [
            "gh", "api", 
            f"/repos/{self.repo}/issues/{self.pr}/comments",
            "--paginate"
        ]
        
        comments = self.run_gh_command(cmd)
        if not comments:
            print("❌ Hiç yorum bulunamadı, varsayılan tarih kullanılacak.")
            return "2025-08-01T00:00:00Z"
        
        # Senin yorumlarını bul ve "/gemini review" içerenleri filtrele
        gemini_review_comments = []
        for comment in comments:
            if isinstance(comment, dict):
                # Authenticated user'ın yorumları ve "/gemini review" içerenler
                if (comment.get('user', {}).get('login') == self.username and 
                    '/gemini review' in comment.get('body', '').lower()):
                    gemini_review_comments.append({
                        'date': comment['created_at'],
                        'body': comment['body']
                    })
        
        if not gemini_review_comments:
            print("❌ '/gemini review' yorumu bulunamadı, varsayılan tarih kullanılacak.")
            return "2025-08-01T00:00:00Z"
        
        # En son tarihi bul
        gemini_review_comments.sort(key=lambda x: x['date'], reverse=True)
        last_review = gemini_review_comments[0]
        
        print(f"✅ Son '/gemini review' yorumu bulundu: {last_review['date']}")
        print(f"   İçerik: {last_review['body']}")
        
        return last_review['date']
    
    def get_reviews_after_date(self) -> List[Dict[str, Any]]:
        """PR reviews'ları getir ve tarihe göre filtrele"""
        print(f"🔍 {self.repo} PR #{self.pr} için reviews getiriliyor...")
        
        cmd = [
            "gh", "api", 
            f"/repos/{self.repo}/pulls/{self.pr}/reviews",
            "--paginate"
        ]
        
        reviews = self.run_gh_command(cmd)
        if not reviews:
            return []
        
        # Gemini Code Assist reviews'larını filtrele
        gemini_reviews = []
        cutoff_time = datetime.datetime.fromisoformat(self.last_review_time.replace('Z', '+00:00'))
        
        print(f"🔍 Kesme zamanı: {cutoff_time}")
        
        for review in reviews:
            if isinstance(review, dict) and review.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                # Reviews için 'submitted_at' kullan, 'created_at' değil
                date_field = review.get('submitted_at')
                if not date_field:
                    print(f"⚠️  Review'da tarih field'ı yok: {review.keys()}")
                    continue
                review_time = datetime.datetime.fromisoformat(date_field.replace('Z', '+00:00'))
                print(f"🤖 Gemini review bulundu: {date_field} | Durum: {'✅ DAHIL' if review_time >= cutoff_time else '❌ HARİÇ'}")
                if review_time >= cutoff_time:
                    gemini_reviews.append({
                        'type': 'review',
                        'date': date_field,
                        'state': review['state'],
                        'body': review['body'],
                        'html_url': review['html_url']
                    })
        
        return gemini_reviews
    
    def get_review_comments_after_date(self) -> List[Dict[str, Any]]:
        """PR review comments'larını getir ve tarihe göre filtrele"""
        print(f"🔍 {self.repo} PR #{self.pr} için review comments getiriliyor...")
        
        cmd = [
            "gh", "api", 
            f"/repos/{self.repo}/pulls/{self.pr}/comments",
            "--paginate"
        ]
        
        comments = self.run_gh_command(cmd)
        if not comments:
            return []
        
        # Gemini Code Assist review comments'larını filtrele
        gemini_comments = []
        cutoff_time = datetime.datetime.fromisoformat(self.last_review_time.replace('Z', '+00:00'))
        
        for comment in comments:
            if isinstance(comment, dict) and comment.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                comment_time = datetime.datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00'))
                if comment_time >= cutoff_time:
                    gemini_comments.append({
                        'type': 'line_comment',
                        'date': comment['created_at'],
                        'file': comment.get('path'),
                        'line': comment.get('line'),
                        'body': comment['body'],
                        'html_url': comment['html_url']
                    })
        
        return gemini_comments
    
    def get_issue_comments_after_date(self) -> List[Dict[str, Any]]:
        """PR issue comments'larını getir ve tarihe göre filtrele"""
        print(f"🔍 {self.repo} PR #{self.pr} için issue comments getiriliyor...")
        
        cmd = [
            "gh", "api", 
            f"/repos/{self.repo}/issues/{self.pr}/comments",
            "--paginate"
        ]
        
        comments = self.run_gh_command(cmd)
        if not comments:
            return []
        
        # Gemini Code Assist issue comments'larını filtrele
        gemini_comments = []
        cutoff_time = datetime.datetime.fromisoformat(self.last_review_time.replace('Z', '+00:00'))
        
        for comment in comments:
            if isinstance(comment, dict) and comment.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                comment_time = datetime.datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00'))
                if comment_time >= cutoff_time:
                    gemini_comments.append({
                        'type': 'issue_comment',
                        'date': comment['created_at'],
                        'body': comment['body'],
                        'html_url': comment['html_url']
                    })
        
        return gemini_comments
    
    def format_comment_for_display(self, comment: Dict[str, Any]) -> str:
        """Yorumu görüntüleme için formatla"""
        lines = []
        
        # Tür ve tarih
        if comment['type'] == 'review':
            lines.append(f"📝 REVIEW")
            lines.append(f"✅ Durum: {comment['state']}")
        elif comment['type'] == 'line_comment':
            lines.append(f"📝 LINE_COMMENT")
            if comment.get('file'):
                lines.append(f"📁 Dosya: {comment['file']}")
            if comment.get('line'):
                lines.append(f"📍 Satır: {comment['line']}")
        elif comment['type'] == 'issue_comment':
            lines.append(f"📝 ISSUE_COMMENT")
        
        lines.append(f"📅 Tarih: {comment['date']}")
        lines.append(f"🔗 Link: {comment['html_url']}")
        
        # İçeriği kısalt
        body = comment['body']
        if len(body) > 500:
            body = body[:500] + "... (devamı için linke tıklayın) ..."
        
        lines.append(f"💬 İçerik:")
        lines.append(f"   {body.replace(chr(10), chr(10) + '   ')}")
        
        return "\n".join(lines)
    
    def fetch_and_display(self):
        """Tüm Gemini yorumlarını getir ve görüntüle"""
        print(f"🚀 Senin son '/gemini review' yorumundan sonraki Gemini Code Assist değerlendirmeleri getiriliyor...")
        print(f"📅 Son yorum tarihi: {self.last_review_time}")
        print("=" * 80)
        
        all_comments = []
        
        # Reviews
        reviews = self.get_reviews_after_date()
        all_comments.extend(reviews)
        
        # Review comments (line comments)
        review_comments = self.get_review_comments_after_date()
        all_comments.extend(review_comments)
        
        # Issue comments
        issue_comments = self.get_issue_comments_after_date()
        all_comments.extend(issue_comments)
        
        # Önce tip'e göre sonra tarihe göre sırala
        # Öncelik sırası: review -> line_comment -> issue_comment
        type_priority = {'review': 0, 'line_comment': 1, 'issue_comment': 2}
        all_comments.sort(key=lambda x: (type_priority.get(x['type'], 3), x['date']))
        
        if not all_comments:
            print("❌ Senin son yorumundan sonra Gemini Code Assist değerlendirmesi bulunamadı.")
            return
        
        print(f"🤖 Senin son yorumundan sonra toplam {len(all_comments)} Gemini Code Assist değerlendirmesi bulundu:")
        print()
        
        for i, comment in enumerate(all_comments, 1):
            print("=" * 80)
            print()
            print(f"{i}. {self.format_comment_for_display(comment)}")
            print("-" * 80)
        
        # JSON olarak kaydet
        output_file = f"gemini_after_last_review_pr{self.pr}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_comments, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Yorumlar '{output_file}' dosyasına kaydedildi.")
        print(f"📊 Özet:")
        print(f"   📝 Reviews: {len(reviews)}")
        print(f"   💬 Line Comments: {len(review_comments)}")
        print(f"   🗨️  Issue Comments: {len(issue_comments)}")
        print(f"   📅 Son yorum tarihi: {self.last_review_time}")

def main():
    parser = argparse.ArgumentParser(description="Son '/gemini review' yorumundan sonraki Gemini Code Assist değerlendirmelerini getir")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--pr", type=int, help="Pull Request numarası (belirtilmezse son PR kullanılır)")
    parser.add_argument("--username", help="GitHub username (varsayılan: authenticated user)")
    
    args = parser.parse_args()
    
    fetcher = GeminiAfterLastReviewFetcher(args.repo, args.pr, args.username)
    fetcher.fetch_and_display()

if __name__ == "__main__":
    main()
