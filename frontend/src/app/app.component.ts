import { Component, inject, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { LandingPageComponent } from './components/landing-page/landing-page.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, LandingPageComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent implements OnInit {
  title = 'frontend';

  private http = inject(HttpClient);
  message = 'loading...';
  imageUrl = '';

  ngOnInit(): void {
    this.http.get<ApiResponse>('http://localhost:8000/api/test').subscribe({
      next: (response) => {
        this.message = response.message;
        this.imageUrl = response.image_url;
      },
      error: (err) => {
        this.message = 'Error connecting to django API';
      }
    });
  }
}

export interface ApiResponse {
  message: string;
  image_url: string;
}
